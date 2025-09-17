import secrets
import string
import random
import uuid
from datetime import datetime, timedelta
from passlib.hash import bcrypt
from flask_mail import Message
from src.extensions import db, mail
from user.user import User
from user.models import PasswordResetToken
from user.exceptions import InvalidOtpException, OtpExpiredException, ResourceNotFoundException

class PasswordResetService:

    @staticmethod
    def initiate_password_reset(email: str):
        user = User.query.filter_by(email=email).first()
        if not user:
            raise ResourceNotFoundException(f"User not found with email: {email}")

        # Delete old token
        PasswordResetToken.query.filter_by(email=user.email).delete()
        db.session.commit()

        # Generate 6-digit OTP
        otp = f"{random.randint(0, 999999):06d}"

        # Save token
        reset_token = PasswordResetToken(
            token=otp,
            email=user.email,
            expiry_date=datetime.utcnow() + timedelta(minutes=5)
        )
        print(f"Creating password reset token: OTP={otp}, Email={user.email}")
        db.session.add(reset_token)
        db.session.commit()
        print(f"Token saved successfully with ID: {reset_token.id}")

        # Verify token was saved
        saved_token = PasswordResetToken.query.filter_by(token=otp).first()
        print(f"Verification - Token found in DB: {saved_token is not None}")
        
        # Send email
        body = f"""Hello {user.username},

You have requested to reset your password for BillDash.

Your One-Time Password (OTP) for password reset is: {otp}

Reset Details:
- Email: {user.email}
- Request Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
- OTP Valid Until: {(datetime.utcnow() + timedelta(minutes=5)).strftime('%Y-%m-%d %H:%M:%S')} UTC

Security Information:
- This OTP is valid for 5 minutes only
- Please do not share this code with anyone
- If you did not request this password reset, please contact your administrator immediately

For support, contact your system administrator.

Best regards,
BillDash"""
        msg = Message("Password Reset OTP - BillDash", recipients=[user.email], body=body)
        mail.send(msg)

    @staticmethod
    def reset_password(email: str, otp: str, new_password: str):
        token = PasswordResetToken.query.filter_by(token=otp).first()
        if not token:
            raise InvalidOtpException("Invalid OTP")

        if token.email != email:
            raise InvalidOtpException("OTP does not match email")

        if token.expiry_date < datetime.utcnow():
            db.session.delete(token)
            db.session.commit()
            raise OtpExpiredException("OTP has expired")

        user = User.query.filter_by(email=email).first()
        if not user:
            raise ResourceNotFoundException(f"User not found with email: {email}")

        user.password = bcrypt.hash(new_password)
        db.session.commit()

        # Send acknowledgment email
        body = f"""Hello {user.username},

Your password has been successfully reset for BillDash.

Reset Confirmation:
- Email: {user.email}
- Reset Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
- Status: Password Updated Successfully

Security Information:
- Please use your new password for future logins
- Your old password is no longer valid
- If you did not perform this reset, please contact your administrator immediately

For support, contact your system administrator.

Best regards,
BillDash"""
        msg = Message("Password Reset Successful - BillDash", recipients=[user.email], body=body)
        mail.send(msg)

        db.session.delete(token)
        db.session.commit()

    @staticmethod
    def verify_reset_otp_only(otp: str) -> str:
        otp_str = str(otp)
        print(f"Looking for OTP: {otp_str}")
        token = PasswordResetToken.query.filter_by(token=otp_str).first()
        print(f"Found token: {token}")
        if not token:
            raise InvalidOtpException("Invalid OTP")

        print(f"Token expiry: {token.expiry_date}, Current time: {datetime.utcnow()}")
        if token.expiry_date < datetime.utcnow():
            db.session.delete(token)
            db.session.commit()
            raise OtpExpiredException("OTP has expired")

        # Generate reset token for password change
        reset_token = str(uuid.uuid4())
        token.token = reset_token
        token.expiry_date = datetime.utcnow() + timedelta(minutes=10)  # 10 minutes for password reset
        db.session.commit()
        print(f"Generated reset token: {reset_token}")
        
        return reset_token

    @staticmethod
    def verify_reset_otp(email: str, otp: str) -> str:
        token = PasswordResetToken.query.filter_by(token=otp).first()
        if not token:
            raise InvalidOtpException("Invalid OTP")

        if token.email != email:
            raise InvalidOtpException("OTP does not match email")

        if token.expiry_date < datetime.utcnow():
            db.session.delete(token)
            db.session.commit()
            raise OtpExpiredException("OTP has expired")

        # Generate reset token for password change
        reset_token = str(uuid.uuid4())
        token.token = reset_token
        token.expiry_date = datetime.utcnow() + timedelta(minutes=10)  # 10 minutes for password reset
        db.session.commit()
        
        return reset_token

    @staticmethod
    def reset_password_with_token(reset_token: str, new_password: str):
        token = PasswordResetToken.query.filter_by(token=reset_token).first()
        if not token:
            raise InvalidOtpException("Invalid reset token")

        if token.expiry_date < datetime.utcnow():
            db.session.delete(token)
            db.session.commit()
            raise OtpExpiredException("Reset token has expired")

        user = User.query.filter_by(email=token.email).first()
        if not user:
            raise ResourceNotFoundException(f"User not found with email: {token.email}")

        user.password = bcrypt.hash(new_password)
        db.session.commit()

        # Send acknowledgment email
        body = f"""Hello {user.username},

Your password has been successfully reset for BillDash.

Reset Confirmation:
- Email: {user.email}
- Reset Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
- Status: Password Updated Successfully

Security Information:
- Please use your new password for future logins
- Your old password is no longer valid
- If you did not perform this reset, please contact your administrator immediately

For support, contact your system administrator.

Best regards,
BillDash"""
        msg = Message("Password Reset Successful - BillDash", recipients=[user.email], body=body)
        mail.send(msg)

        db.session.delete(token)
        db.session.commit()

    @staticmethod
    def generate_temporary_password(user: User):
        temp_password = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(12))
        user.password = bcrypt.hash(temp_password)
        db.session.commit()

        subject = "Welcome to the Company!"
        body = (f"<p>Hi {user.username},</p>"
                f"<p>Your account has been created. Temporary password: <b>{temp_password}</b></p>"
                f"<p><a href='https://your-app.com/login'>Login</a></p>")
        msg = Message(subject, recipients=[user.email], html=body)
        mail.send(msg)

    @staticmethod
    def get_user_by_token(token: str) -> User:
        reset_token = PasswordResetToken.query.filter_by(token=token).first()
        if not reset_token:
            raise InvalidOtpException("Invalid or expired token")

        if reset_token.expiry_date < datetime.utcnow():
            db.session.delete(reset_token)
            db.session.commit()
            raise OtpExpiredException("Token has expired")

        user = User.query.filter_by(email=reset_token.email).first()
        if not user:
            raise ResourceNotFoundException("User not found for token email")
        return user

    @staticmethod
    def invalidate_token(token: str):
        reset_token = PasswordResetToken.query.filter_by(token=token).first()
        if reset_token:
            db.session.delete(reset_token)
            db.session.commit()