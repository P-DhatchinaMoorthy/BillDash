from flask import Blueprint, request, jsonify, session, g
from user.user import User, Permission, UserPermission, AuditLog
from src.extensions import db
from functools import wraps
from user.jwt_utils import generate_jwt_token
from user.jwt_middleware import jwt_required, get_current_user
from user.audit_logger import log_user_action, audit_decorator

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

@bp.route('/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    username = data.get('username') or data.get('user_id')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400
    
    user = User.query.filter_by(username=username).first()
    if user and user.check_password(password):
        # Generate JWT token
        token = generate_jwt_token(user)
        
        # Set user in g for audit logging
        g.current_user = {
            'user_id': user.id,
            'username': user.username,
            'role': user.role
        }
        
        # Log login action
        log_user_action('LOGIN', 'auth', user.id)
        
        return jsonify({
            'success': True,
            'token': token,
            'user': {
                'user_id': user.id,
                'username': user.username,
                'role': user.role
            }
        }), 200
    
    return jsonify({'error': 'Invalid credentials'}), 401

@bp.route('/logout', methods=['POST'])
def logout():
    from flask import session
    session.clear()
    return jsonify({'success': True, 'message': 'Logged out successfully'})



@bp.route('/admin/user-permissions/<int:user_id>', methods=['GET'])
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

@bp.route('/admin/audit-logs', methods=['GET'])
@jwt_required
def get_audit_logs():
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 50))
    
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    result = [{
        'id': log.id,
        'user_id': log.user_id,
        'action': log.action,
        'module_name': log.module_name,
        'record_id': log.record_id,
        'ip_address': log.ip_address,
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

@bp.route('/admin/user-permissions/<int:user_id>', methods=['PUT'])
@jwt_required
@audit_decorator('user_permissions', 'UPDATE')
def update_user_permissions(user_id):
    data = request.get_json() or {}
    permissions = data.get('permissions', {})
    
    if not permissions:
        return jsonify({'error': 'permissions required'}), 400
    
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
        return jsonify({'success': True}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@bp.route('/admin/create_user', methods=['POST'])
@jwt_required
@audit_decorator('users', 'CREATE')
def create_user():
    data = request.get_json() or {}
    username = data.get('username')
    email = data.get('email')
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
            password=password,
            role=role
        )
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
        return jsonify({
            'success': True,
            'message': 'User created successfully',
            'user': {
                'user_id': user.id,
                'username': user.username,
                'email': user.email,
                'role': user.role
            }
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to create user: {str(e)}'}), 500