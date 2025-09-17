from flask import Blueprint, request, jsonify, session, g
from user.user import User, Permission, UserPermission, AuditLog
from src.extensions import db
from functools import wraps
from user.jwt_utils import generate_tokens, refresh_access_token, decode_refresh_token
from user.jwt_middleware import jwt_required, get_current_user
from user.audit_logger import log_user_action, audit_decorator
from user.two_fa_service import TwoFaService
from user.password_reset_service import PasswordResetService
from user.exceptions import InvalidOtpException, OtpExpiredException, ResourceNotFoundException, InvalidTokenException
from mail_invoice.email_service import EmailService
import secrets
import string

def require_permission(module, action):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user_id = session.get('user_id')
            if not user_id:
                return jsonify({'error': 'Login required'}), 401
            
            user = User.query.get(user_id)
            if not user:
                return jsonify({'error': 'User not found'}), 401
            
            # Admin bypasses all permission checks
            if user.role == 'admin':
                return f(*args, **kwargs)
            
            # For admin module, only admin role is allowed
            if module == 'admin':
                return jsonify({'error': 'Access denied'}), 403
            
            permission = Permission.query.filter_by(module_name=module).first()
            if not permission:
                return jsonify({'error': 'Access denied'}), 403
            
            user_perm = UserPermission.query.filter_by(
                user_id=user_id, permission_id=permission.id
            ).first()
            
            if not user_perm:
                return jsonify({'error': 'Access denied'}), 403
            
            allowed = {
                'read': user_perm.can_read,
                'write': user_perm.can_write,
                'delete': user_perm.can_delete
            }.get(action, False)
            
            if not allowed:
                return jsonify({'error': 'Access denied'}), 403
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

bp = Blueprint('user', __name__)
two_fa_service = TwoFaService()

@bp.route('/login/', methods=['POST'])
def login():
    data = request.get_json() or {}
    email = data.get('email')
    password = data.get('password')
    
    if not email or not password:
        return jsonify({'error': 'Email and password required'}), 400
    
    user = User.query.filter_by(email=email).first()
    if user and user.check_password(password):
        # All users require 2FA
        if not user.email:
            return jsonify({'error': 'Email required for 2FA'}), 400
            
        try:
            temp_token = two_fa_service.send_2fa_code(user)
            return jsonify({
                'success': True,
                'requires_2fa': True,
                'temp_token': temp_token,
                'message': 'OTP sent to your email'
            }), 200
        except Exception as e:
            return jsonify({'error': 'Failed to send OTP'}), 500
    
    return jsonify({'error': 'Invalid credentials'}), 401

@bp.route('/verify-2fa/', methods=['POST'])
def verify_2fa():
    data = request.get_json() or {}
    temp_token = data.get('temp_token')
    otp = data.get('otp')
    
    if not temp_token or not otp:
        return jsonify({'error': 'temp_token and otp required'}), 400
    
    try:
        user = two_fa_service.verify_2fa(temp_token, otp)
        tokens = generate_tokens(user)
        
        g.current_user = {
            'user_id': user.id,
            'username': user.username,
            'role': user.role
        }
        log_user_action('LOGIN', 'auth', user.id)
        
        return jsonify({
            'success': True,
            'access_token': tokens['access_token'],
            'refresh_token': tokens['refresh_token'],
            'access_expires_in': tokens['access_expires_in'],
            'refresh_expires_in': tokens['refresh_expires_in'],
            'token_type': tokens['token_type'],
            'user': {
                'user_id': user.id,
                'username': user.username,
                'role': user.role
            }
        }), 200
    except InvalidOtpException:
        return jsonify({'error': 'Invalid OTP'}), 400
    except OtpExpiredException:
        return jsonify({'error': 'OTP expired'}), 400
    except InvalidTokenException:
        return jsonify({'error': 'Invalid temp token'}), 400
    except Exception as e:
        return jsonify({'error': 'Verification failed'}), 500

@bp.route('/resend-otp', methods=['POST'])
def resend_otp():
    data = request.get_json() or {}
    temp_token = data.get('temp_token')
    
    if not temp_token:
        return jsonify({'error': 'temp_token required'}), 400
    
    try:
        email = two_fa_service.get_email_from_temp_token(temp_token)
        if not email:
            return jsonify({'error': 'Invalid temp token'}), 400
            
        two_fa_service.resend_otp(email)
        return jsonify({'success': True, 'message': 'OTP resent'}), 200
    except Exception as e:
        return jsonify({'error': 'Failed to resend OTP'}), 500

@bp.route('/logout', methods=['POST'])
def logout():
    return jsonify({'success': True, 'message': 'Logged out successfully'})

@bp.route('/refresh', methods=['POST'])
def refresh_token():
    """Refresh access token using refresh token"""
    data = request.get_json()
    if not data:
        return jsonify({
            'error': 'JSON data required',
            'error_code': 'NO_JSON_DATA'
        }), 400
        
    refresh_token = data.get('refresh_token')
    
    if not refresh_token:
        return jsonify({
            'error': 'Refresh token required',
            'error_code': 'REFRESH_TOKEN_MISSING'
        }), 400
    
    # Validate refresh token and generate new access token
    result = refresh_access_token(refresh_token)
    if not result:
        return jsonify({
            'error': 'Invalid or expired refresh token',
            'error_code': 'REFRESH_TOKEN_INVALID'
        }), 401
    
    return jsonify({
        'success': True,
        'access_token': result['access_token'],
        'expires_in': result['expires_in'],
        'token_type': result['token_type']
    }), 200

@bp.route('/verify-token', methods=['POST'])
def verify_token():
    """Verify if access token is valid"""
    from user.jwt_utils import decode_access_token
    
    data = request.get_json() or {}
    token = data.get('access_token')
    
    if not token:
        return jsonify({
            'valid': False,
            'error': 'Token required'
        }), 400
    
    payload = decode_access_token(token)
    if payload:
        return jsonify({
            'valid': True,
            'user_id': payload['user_id'],
            'username': payload['username'],
            'role': payload['role'],
            'expires_at': payload['exp']
        }), 200
    else:
        return jsonify({
            'valid': False,
            'error': 'Invalid or expired token'
        }), 401

@bp.route('/me/', methods=['GET'])
@jwt_required
def get_current_user_details():
    """Get current logged-in user details for dashboard"""
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'User not authenticated'}), 401
    
    # Fetch full user details from database
    user = User.query.get(current_user['user_id'])
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    # Get user permissions
    permissions = db.session.query(
        Permission.module_name,
        UserPermission.can_read,
        UserPermission.can_write,
        UserPermission.can_delete
    ).join(UserPermission).filter(
        UserPermission.user_id == user.id
    ).all()
    
    user_permissions = {}
    for perm in permissions:
        user_permissions[perm.module_name] = {
            'read': perm.can_read,
            'write': perm.can_write,
            'delete': perm.can_delete
        }
    
    return jsonify({
        'success': True,
        'user': {
            'user_id': user.id,
            'username': user.username,
            'email': user.email,
            'phone_number': user.phone_number,
            'role': user.role,
            'created_at': user.created_at.isoformat(),
            'updated_at': user.updated_at.isoformat() if user.updated_at else None,
            'permissions': user_permissions
        }
    }), 200


@bp.route('/admin/users/', methods=['GET'])
@jwt_required
def get_all_users():
    current_user = get_current_user()
    if not current_user or current_user['role'] != 'admin':
        return jsonify({'error': 'Admin access required'}), 403
    
    users = User.query.filter(User.role != 'admin').all()
    return jsonify({
        'users': [{
            'user_id': user.id,
            'username': user.username,
            'email': user.email,
            'phone_number': user.phone_number,
            'role': user.role,
            'created_at': user.created_at.isoformat(),
            'updated_at': user.updated_at.isoformat() if user.updated_at else None
        } for user in users]
    }), 200

@bp.route('/admin/user-permissions/<int:user_id>/', methods=['GET'])
@jwt_required
def get_user_permissions(user_id):
    # Get user details
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    # Get user permissions
    permissions = db.session.query(
        Permission.module_name,
        UserPermission.can_read,
        UserPermission.can_write,
        UserPermission.can_delete,
    ).join(UserPermission).filter(
        UserPermission.user_id == user_id
    ).all()
    
    permission_list = [{
        'module_name': p.module_name,
        'can_read': p.can_read,
        'can_write': p.can_write,
        'can_delete': p.can_delete
    } for p in permissions]
    
    return jsonify({
        'user': {
            'user_id': user.id,
            'username': user.username,
            'email': getattr(user, 'email', None),
            'role': user.role,
            'created_at': user.created_at.isoformat(),
            'updated_at': user.updated_at.isoformat() if user.updated_at else None
        },
        'permissions': permission_list
    }), 200

@bp.route('/admin/audit-logs/', methods=['GET'])
@jwt_required
def get_audit_logs():
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 50))
    
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    result = [{
        'user_id': log.user_id,
        'username': log.username,
        'role': log.user_role,
        'action': log.action,
        'module_name': log.module_name,
        'new_data': log.new_data,
        'timestamp': log.timestamp.isoformat()
    } for log in logs.items]
    
    return jsonify({
        'logs': result,
        'pagination': {
            'page': logs.page,
            'per_page': logs.per_page,
            'total': logs.total,
            'pages': logs.pages
        }
    }), 200

@bp.route('/admin/user-permissions/<int:user_id>/', methods=['PUT'])
@jwt_required
def update_user_permissions(user_id):
    data = request.get_json() or {}
    permissions = data.get('permissions', {})
    
    if not permissions:
        return jsonify({'error': 'permissions required'}), 400
    
    # Get old permissions for audit logging
    old_permissions = {}
    existing_perms = db.session.query(
        Permission.module_name,
        UserPermission.can_read,
        UserPermission.can_write,
        UserPermission.can_delete
    ).join(UserPermission).filter(
        UserPermission.user_id == user_id
    ).all()
    
    for perm in existing_perms:
        old_permissions[perm.module_name] = {
            'read': perm.can_read,
            'write': perm.can_write,
            'delete': perm.can_delete
        }
    
    try:
        for module, perms in permissions.items():
            permission = Permission.query.filter_by(module_name=module).first()
            if not permission:
                continue
            
            user_perm = UserPermission.query.filter_by(
                user_id=user_id, permission_id=permission.id
            ).first()
            
            if not user_perm:
                user_perm = UserPermission(
                    user_id=user_id,
                    permission_id=permission.id
                )
                db.session.add(user_perm)
            
            user_perm.can_read = perms.get('read', False)
            user_perm.can_write = perms.get('write', False)
            user_perm.can_delete = perms.get('delete', False)
            user_perm.granted_by = get_current_user()['user_id']
        
        db.session.commit()
        
        # Log the permission update with detailed info
        log_user_action(
            action='UPDATE',
            module='user_permissions',
            record_id=user_id,
            old_data=old_permissions,
            new_data=permissions,
            target_user_id=user_id
        )
        
        return jsonify({'success': True}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@bp.route('/admin/create_user/', methods=['POST'])
@jwt_required
@audit_decorator('users', 'CREATE')
def create_user():
    data = request.get_json() or {}
    username = data.get('username')
    email = data.get('email')
    phone_number = data.get('phone_number')
    password = data.get('password')
    role = data.get('role')
    permissions = data.get('permissions', {})
    
    # Validate required fields
    if not username or not password or not role:
        return jsonify({'error': 'username, password and role are required'}), 400
    
    # Validate role
    valid_roles = ['admin', 'manager', 'sales', 'accountant', 'stock_manager']
    if role not in valid_roles:
        return jsonify({'error': f'Invalid role. Must be one of: {valid_roles}'}), 400
    
    # Validate username format
    if len(username) < 3:
        return jsonify({'error': 'Username must be at least 3 characters long'}), 400
    
    # Validate password strength
    if len(password) < 6:
        return jsonify({'error': 'Password must be at least 6 characters long'}), 400
    
    # Check if username already exists
    existing_user = User.query.filter_by(username=username).first()
    if existing_user:
        return jsonify({'error': f'Username "{username}" already exists'}), 400
    
    # Check if email already exists (if provided)
    if email:
        existing_email = User.query.filter_by(email=email).first()
        if existing_email:
            return jsonify({'error': f'Email "{email}" already exists'}), 400
    
    try:
        # Create user
        user = User(
            username=username,
            email=email,
            phone_number=phone_number,
            role=role
        )
        user.set_password(password)
        db.session.add(user)
        db.session.flush()
        
        # Set permissions if provided
        for module, perms in permissions.items():
            if not isinstance(perms, dict):
                continue
                
            permission = Permission.query.filter_by(module_name=module).first()
            if not permission:
                permission = Permission(module_name=module)
                db.session.add(permission)
                db.session.flush()
            
            user_perm = UserPermission(
                user_id=user.id,
                permission_id=permission.id,
                can_read=bool(perms.get('read', False)),
                can_write=bool(perms.get('write', False)),
                can_delete=bool(perms.get('delete', False)),
                granted_by=get_current_user()['user_id']
            )
            db.session.add(user_perm)
        
        db.session.commit()
        
        # Send credentials via email if email is provided
        email_sent = False
        email_message = ''
        if email:
            try:
                email_service = EmailService()
                email_result = email_service.send_user_credentials_email(
                    user_email=email,
                    username=username,
                    password=password,
                    role=role
                )
                if email_result['success']:
                    email_sent = True
                    email_message = ' Login credentials sent to user email.'
                else:
                    email_message = f' Warning: Failed to send email - {email_result["error"]}'
            except Exception as e:
                email_message = f' Warning: Failed to send email - {str(e)}'
        
        message = 'User created successfully' + email_message
            
        return jsonify({
            'success': True,
            'message': message,
            'email_sent': email_sent,
            'user': {
                'user_id': user.id,
                'username': user.username,
                'email': user.email,
                'phone_number': user.phone_number,
                'role': user.role
            }
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to create user: {str(e)}'}), 500
