from functools import wraps
from flask import request, jsonify, g
from user.user import User, Permission, UserPermission
from user.jwt_middleware import jwt_required, get_current_user
from user.audit_logger import log_user_action
from src.extensions import db

def require_permission_jwt(module, action=None):
    """JWT-based permission decorator with audit logging"""
    def decorator(f):
        @wraps(f)
        @jwt_required
        def decorated_function(*args, **kwargs):
            current_user = get_current_user()
            user_id = current_user['user_id']
            
            # Get user from database
            user = User.query.get(user_id)
            if not user:
                return jsonify({'error': 'User not found'}), 401
            
            # Admin bypasses all permission checks
            if user.role == 'admin':
                result = f(*args, **kwargs)
                # Log admin action
                action_name = action or request.method.lower()
                record_id = kwargs.get('id') or kwargs.get('customer_id') or kwargs.get('user_id')
                # Safely get JSON data (None if not JSON request)
                json_data = None
                try:
                    if request.is_json:
                        json_data = request.get_json()
                except:
                    pass
                log_user_action(action_name.upper(), module, record_id, None, json_data)
                return result
            
            # Auto-detect action from HTTP method if not specified
            if action is None:
                method_actions = {
                    'GET': 'read',
                    'POST': 'write', 
                    'PUT': 'write',
                    'PATCH': 'write',
                    'DELETE': 'delete'
                }
                detected_action = method_actions.get(request.method, 'read')
            else:
                detected_action = action
            
            # Check permission
            perm_query = db.session.query(UserPermission).join(Permission).filter(
                UserPermission.user_id == user_id,
                Permission.module_name == module
            ).first()
            
            if not perm_query:
                return jsonify({'error': 'Access denied'}), 403
            
            allowed = {
                'read': perm_query.can_read,
                'write': perm_query.can_write,
                'delete': perm_query.can_delete
            }.get(detected_action, False)
            
            if not allowed:
                return jsonify({'error': 'Access denied'}), 403
            
            # Execute function
            result = f(*args, **kwargs)
            
            # Log successful action
            record_id = kwargs.get('id') or kwargs.get('customer_id') or kwargs.get('user_id')
            # Safely get JSON data (None if not JSON request)
            json_data = None
            try:
                if request.is_json:
                    json_data = request.get_json()
            except:
                pass
            log_user_action(detected_action.upper(), module, record_id, None, json_data)
            
            return result
        return decorated_function
    return decorator