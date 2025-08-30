from flask import request, jsonify, g
from flask_login import current_user
from functools import wraps
from .permission_service import PermissionService

def init_auth_middleware(app):
    """Initialize authentication middleware"""
    
    @app.before_request
    def load_user_permissions():
        """Load user permissions before each request"""
        if current_user.is_authenticated:
            g.user_permissions = {}
            # Cache user permissions for the request
            if current_user.role.name == 'Admin':
                g.user_permissions = {'admin': True}
            else:
                # Load specific permissions
                permissions = PermissionService.get_permissions_for_role(current_user.role.name)
                for perm in permissions:
                    g.user_permissions[perm] = current_user.has_permission(perm)

def check_api_permission(permission_name):
    """Check if user has API permission"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return jsonify({'error': 'Authentication required'}), 401
            
            if not current_user.has_permission(permission_name):
                PermissionService.log_action(
                    current_user.id, 'ACCESS_DENIED', permission_name,
                    success=False, error_message='Insufficient permissions'
                )
                return jsonify({'error': 'Insufficient permissions'}), 403
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def get_permission_for_method(resource, method):
    """Map HTTP methods to permission actions"""
    method_mapping = {
        'GET': 'read',
        'POST': 'create',
        'PUT': 'update',
        'PATCH': 'update',
        'DELETE': 'delete'
    }
    action = method_mapping.get(method, 'read')
    return f"{resource}.{action}"