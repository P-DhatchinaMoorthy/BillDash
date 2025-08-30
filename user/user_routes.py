from flask import Blueprint, request, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from .user import User, Role, Permission, RolePermission, UserPermission, AuditLog
from .permission_service import require_permission, PermissionService
from src.extensions import db

user_bp = Blueprint('user', __name__, url_prefix='/api/users')

@user_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    user = User.query.filter_by(username=username).first()
    
    if user and user.check_password(password) and user.is_active:
        login_user(user)
        PermissionService.log_action(user.id, 'LOGIN', 'AUTH')
        return jsonify({
            'message': 'Login successful',
            'user': {
                'id': user.id,
                'username': user.username,
                'role': user.role.name
            }
        })
    
    PermissionService.log_action(
        user.id if user else None, 'LOGIN_FAILED', 'AUTH',
        success=False, error_message='Invalid credentials'
    )
    return jsonify({'error': 'Invalid credentials'}), 401

@user_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    PermissionService.log_action(current_user.id, 'LOGOUT', 'AUTH')
    logout_user()
    return jsonify({'message': 'Logout successful'})

@user_bp.route('/', methods=['GET'])
@require_permission('users.read')
def get_users():
    users = User.query.all()
    return jsonify([{
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'role': user.role.name,
        'is_active': user.is_active,
        'created_at': user.created_at.isoformat()
    } for user in users])

@user_bp.route('/', methods=['POST'])
@require_permission('users.create')
def create_user():
    data = request.get_json()
    
    if User.query.filter_by(username=data['username']).first():
        return jsonify({'error': 'Username already exists'}), 400
    
    if User.query.filter_by(email=data['email']).first():
        return jsonify({'error': 'Email already exists'}), 400
    
    role = Role.query.get(data['role_id'])
    if not role:
        return jsonify({'error': 'Invalid role'}), 400
    
    user = User(
        username=data['username'],
        email=data['email'],
        role_id=data['role_id']
    )
    user.set_password(data['password'])
    
    db.session.add(user)
    db.session.commit()
    
    PermissionService.log_action(current_user.id, 'CREATE', 'USER', user.id)
    
    return jsonify({
        'message': 'User created successfully',
        'user_id': user.id
    }), 201

@user_bp.route('/<int:user_id>', methods=['PUT'])
@require_permission('users.update')
def update_user(user_id):
    user = User.query.get_or_404(user_id)
    data = request.get_json()
    
    if 'username' in data and data['username'] != user.username:
        if User.query.filter_by(username=data['username']).first():
            return jsonify({'error': 'Username already exists'}), 400
        user.username = data['username']
    
    if 'email' in data and data['email'] != user.email:
        if User.query.filter_by(email=data['email']).first():
            return jsonify({'error': 'Email already exists'}), 400
        user.email = data['email']
    
    if 'role_id' in data:
        role = Role.query.get(data['role_id'])
        if not role:
            return jsonify({'error': 'Invalid role'}), 400
        user.role_id = data['role_id']
    
    if 'is_active' in data:
        user.is_active = data['is_active']
    
    if 'password' in data:
        user.set_password(data['password'])
    
    db.session.commit()
    
    PermissionService.log_action(current_user.id, 'UPDATE', 'USER', user.id)
    
    return jsonify({'message': 'User updated successfully'})

@user_bp.route('/<int:user_id>', methods=['DELETE'])
@require_permission('users.delete')
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    
    if user.id == current_user.id:
        return jsonify({'error': 'Cannot delete your own account'}), 400
    
    db.session.delete(user)
    db.session.commit()
    
    PermissionService.log_action(current_user.id, 'DELETE', 'USER', user_id)
    
    return jsonify({'message': 'User deleted successfully'})

@user_bp.route('/roles', methods=['GET'])
@require_permission('users.read')
def get_roles():
    roles = Role.query.all()
    return jsonify([{
        'id': role.id,
        'name': role.name,
        'description': role.description
    } for role in roles])

@user_bp.route('/permissions/<int:user_id>', methods=['GET'])
@require_permission('users.read')
def get_user_permissions(user_id):
    user = User.query.get_or_404(user_id)
    permissions = UserPermission.query.filter_by(user_id=user_id).all()
    
    return jsonify([{
        'permission_name': perm.permission_name,
        'granted': perm.granted,
        'created_at': perm.created_at.isoformat()
    } for perm in permissions])

@user_bp.route('/permissions/<int:user_id>', methods=['POST'])
@require_permission('users.update')
def grant_user_permission(user_id):
    user = User.query.get_or_404(user_id)
    data = request.get_json()
    
    permission = UserPermission.query.filter_by(
        user_id=user_id,
        permission_name=data['permission_name']
    ).first()
    
    if permission:
        permission.granted = data['granted']
    else:
        permission = UserPermission(
            user_id=user_id,
            permission_name=data['permission_name'],
            granted=data['granted'],
            granted_by=current_user.id
        )
        db.session.add(permission)
    
    db.session.commit()
    
    PermissionService.log_action(
        current_user.id, 'GRANT_PERMISSION', 'USER_PERMISSION',
        f"{user_id}:{data['permission_name']}"
    )
    
    return jsonify({'message': 'Permission updated successfully'})

@user_bp.route('/audit', methods=['GET'])
@require_permission('audit.read')
def get_audit_logs():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return jsonify({
        'logs': [{
            'id': log.id,
            'user_id': log.user_id,
            'username': log.user.username if log.user else 'Unknown',
            'action': log.action,
            'resource': log.resource,
            'resource_id': log.resource_id,
            'ip_address': log.ip_address,
            'success': log.success,
            'error_message': log.error_message,
            'timestamp': log.timestamp.isoformat()
        } for log in logs.items],
        'total': logs.total,
        'pages': logs.pages,
        'current_page': page
    })