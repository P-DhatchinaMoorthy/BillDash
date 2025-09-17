from flask import Blueprint, request, jsonify
from user.password_reset_service import PasswordResetService
from user.exceptions import InvalidOtpException, OtpExpiredException, ResourceNotFoundException

bp = Blueprint('password_reset', __name__)

@bp.route('/password-reset/', methods=['POST'])
def forgot_password():
    data = request.get_json() or {}
    email = data.get('email')
    
    if not email:
        return jsonify({'error': 'Email required'}), 400
    
    try:
        PasswordResetService.initiate_password_reset(email)
        return jsonify({
            'success': True,
            'message': 'Password reset OTP sent to your email'
        }), 200
    except ResourceNotFoundException:
        return jsonify({'error': 'Email not found'}), 404
    except Exception as e:
        return jsonify({'error': 'Failed to send reset code'}), 500

@bp.route('/verify-reset-otp/', methods=['POST'])
def verify_reset_otp():
    data = request.get_json() or {}
    otp = data.get('otp')
    
    if not otp:
        return jsonify({'error': 'OTP required'}), 400
    
    try:
        reset_token = PasswordResetService.verify_reset_otp_only(otp)
        return jsonify({
            'success': True,
            'reset_token': reset_token,
            'message': 'OTP verified successfully'
        }), 200
    except InvalidOtpException as e:
        return jsonify({'error': 'Invalid OTP'}), 400
    except OtpExpiredException as e:
        return jsonify({'error': 'OTP has expired'}), 400
    except ResourceNotFoundException as e:
        return jsonify({'error': 'User not found'}), 404
    except Exception as e:
        print(f"OTP verification error: {str(e)}")
        return jsonify({'error': f'OTP verification failed: {str(e)}'}), 500

@bp.route('/password/reset/', methods=['POST'])
def reset_password():
    data = request.get_json() or {}
    reset_token = data.get('reset_token')
    new_password = data.get('new_password')
    confirm_password = data.get('confirm_password')
    
    if not reset_token or not new_password or not confirm_password:
        return jsonify({'error': 'Reset token, new password and confirm password required'}), 400
    
    if len(new_password) < 6:
        return jsonify({'error': 'Password must be at least 6 characters long'}), 400
    
    if new_password != confirm_password:
        return jsonify({'error': 'New password and confirm password do not match'}), 400
    
    try:
        PasswordResetService.reset_password_with_token(reset_token, new_password)
        return jsonify({
            'success': True,
            'message': 'Password reset successfully'
        }), 200
    except InvalidOtpException:
        return jsonify({'error': 'Invalid reset token'}), 400
    except OtpExpiredException:
        return jsonify({'error': 'Reset token has expired'}), 400
    except ResourceNotFoundException:
        return jsonify({'error': 'User not found'}), 404
    except Exception as e:
        return jsonify({'error': 'Password reset failed'}), 500