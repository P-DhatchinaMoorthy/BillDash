from functools import wraps
from flask import request, jsonify, session
from extensions import db
from user.user import User, Permission, UserPermission, AuditLog
import json

def init_auth_middleware(app):
    pass

def check_user_permission(user_id, module, action):
    user = User.query.get(user_id)
    if not user:
        return False
    
    # Admin bypasses all permission checks
    if user.role == 'admin':
        return True
    
    # Regular users check permissions table
    perm_query = db.session.query(UserPermission).join(Permission).filter(
        UserPermission.user_id == user_id,
        Permission.module_name == module
    ).first()
    
    if not perm_query:
        return False
    
    return {
        'read': perm_query.can_read,
        'write': perm_query.can_write,
        'delete': perm_query.can_delete
    }.get(action, False)

def log_user_action(user_id, action, module, data=None, record_id=None):
    try:
        ip_address = request.environ.get('HTTP_X_REAL_IP', request.remote_addr)
        user_agent = request.headers.get('User-Agent')
        
        audit_log = AuditLog(
            user_id=user_id,
            action=action,
            module_name=module,
            record_id=record_id,
            new_data=data,
            ip_address=ip_address,
            user_agent=user_agent
        )
        db.session.add(audit_log)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Audit logging failed: {e}")

METHOD_ACTION_MAP = {
    'GET': 'read',
    'POST': 'write',
    'PUT': 'write',
    'PATCH': 'write',
    'DELETE': 'delete'
}

def require_permission(module, action=None):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Get user_id from session
            user_id = session.get('user_id')
            if not user_id:
                return jsonify({'error': 'Login required'}), 401
            
            # Auto-detect action from HTTP method if not specified
            if action is None:
                detected_action = METHOD_ACTION_MAP.get(request.method, 'read')
            else:
                detected_action = action
            
            # Check permission (admin user bypasses all checks)
            if not check_user_permission(user_id, module, detected_action):
                return jsonify({'error': 'Access denied'}), 403
            
            # Execute the function
            result = f(*args, **kwargs)
            
            # Log the action after successful execution
            try:
                log_user_action(user_id, detected_action.upper(), module, request.get_json())
            except:
                pass  # Skip logging if there are issues
            
            return result
        return decorated_function
    return decorator