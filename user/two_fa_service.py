import uuid
import random
from datetime import datetime, timedelta
from cachetools import TTLCache
from flask_mail import Message
from src.extensions import db, mail
from user.user import User
from user.exceptions import InvalidTokenException, ResourceNotFoundException, OtpExpiredException, InvalidOtpException, OtpResendTooSoonException, LoggingFailureException

class TwoFaService:
    def __init__(self):
        # tempTokenStore equivalent: expires in 5 min
        self.temp_token_store = TTLCache(maxsize=500, ttl=300)

    def send_2fa_code(self, user: User) -> str:
        otp = self._generate_otp()
        user.two_fa_code = otp
        user.two_fa_expiry = datetime.utcnow() + timedelta(minutes=5)
        db.session.commit()

        body = f"""Hello {user.username},

Your One-Time Password (OTP) for BillDash login is: {otp}

This OTP is valid for 5 minutes only. Please do not share this code with anyone.

If you did not request this login, please contact your administrator immediately.

Best regards,
BillDash"""
        mail.send(Message("Your 2FA OTP - BillDash", recipients=[user.email], body=body))

        temp_token = str(uuid.uuid4())
        self.temp_token_store[temp_token] = user.email
        return temp_token

    def verify_2fa(self, temp_token: str, otp: str) -> User:
        email = self.temp_token_store.get(temp_token)
        if email is None:
            raise InvalidTokenException("Invalid temp token")

        user = User.query.filter_by(email=email).first()
        if not user:
            raise ResourceNotFoundException(f"User not found with email: {email}")

        if not user.two_fa_expiry or user.two_fa_expiry < datetime.utcnow():
            raise OtpExpiredException("OTP expired")

        if otp != user.two_fa_code:
            raise InvalidOtpException("Invalid OTP")

        # clear OTP and token
        user.two_fa_code = None
        user.two_fa_expiry = None
        db.session.commit()
        self.temp_token_store.pop(temp_token, None)
        return user

    def get_email_from_temp_token(self, temp_token: str) -> str:
        return self.temp_token_store.get(temp_token)

    def resend_otp(self, email_or_phone: str):
        # find user by email or phone
        user = (User.query.filter_by(email=email_or_phone).first() or
                User.query.filter_by(phone_number=email_or_phone).first())
        if not user:
            raise ResourceNotFoundException(f"User not found with email/phone: {email_or_phone}")

        # ensure temp token exists
        if user.email not in self.temp_token_store.values():
            raise InvalidTokenException("No active 2FA session found. Please log in again.")

        # cooldown: 30 seconds
        if user.last_otp_sent_at and user.last_otp_sent_at + timedelta(seconds=30) > datetime.utcnow():
            raise OtpResendTooSoonException(
                "OTP was recently sent. Please wait 30 seconds before requesting again."
            )

        otp = self._generate_otp()
        user.two_fa_code = otp
        user.two_fa_expiry = datetime.utcnow() + timedelta(minutes=5)
        user.last_otp_sent_at = datetime.utcnow()
        db.session.commit()

        try:
            body = f"""Hello {user.username},

Your One-Time Password (OTP) for BillDash Application login is: {otp}

This OTP is valid for 5 minutes only. Please do not share the OTP with anyone.

If you did not request this login, please contact your administrator immediately.

Best regards,
BillDash Application"""
            mail.send(Message("Your 2FA OTP (Resent) - BillDash Application", recipients=[user.email], body=body))
        except Exception as e:
            raise LoggingFailureException("Failed to send OTP email") from e

    @staticmethod
    def _generate_otp() -> str:
        return f"{random.randint(0, 999999):06d}"