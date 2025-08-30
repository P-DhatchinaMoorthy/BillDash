from flask import request, g
from functools import wraps
from flask_login import current_user
from .user import AuditLog, Permission
from src.extensions import db
import datetime

class PermissionService:
    
    @staticmethod
    def log_action(user_id, action, resource, resource_id=None, success=True, error_message=None):
        """Log user actions for audit trail"""
        audit_log = AuditLog(
            user_id=user_id,
            action=action,
            resource=resource,
            resource_id=str(resource_id) if resource_id else None,
            ip_address=request.remote_addr if request else None,
            user_agent=request.headers.get('User-Agent') if request else None,
            success=success,
            error_message=error_message
        )
        db.session.add(audit_log)
        db.session.commit()
    
    @staticmethod
    def check_permission(permission_name):
        """Check if current user has permission"""
        if not current_user.is_authenticated:
            return False
        return current_user.has_permission(permission_name)
    
    @staticmethod
    def get_permissions_for_role(role_name):
        """Get all permissions for a specific role"""
        permissions = {
            'Admin': [
                'customers.create', 'customers.read', 'customers.update', 'customers.delete',
                'suppliers.create', 'suppliers.read', 'suppliers.update', 'suppliers.delete',
                'categories.create', 'categories.read', 'categories.update', 'categories.delete',
                'products.create', 'products.read', 'products.update', 'products.delete',
                'invoices.create', 'invoices.read', 'invoices.update', 'invoices.delete',
                'payments.create', 'payments.read', 'payments.update', 'payments.delete',
                'purchases.create', 'purchases.read', 'purchases.update', 'purchases.delete',
                'returns.create', 'returns.read', 'returns.update', 'returns.delete',
                'reports.read', 'reports.generate',
                'users.create', 'users.read', 'users.update', 'users.delete',
                'audit.read'
            ],
            'Manager': [
                'customers.create', 'customers.read', 'customers.update',
                'suppliers.create', 'suppliers.read', 'suppliers.update',
                'categories.create', 'categories.read', 'categories.update',
                'products.create', 'products.read', 'products.update',
                'invoices.create', 'invoices.read', 'invoices.update',
                'payments.create', 'payments.read', 'payments.update',
                'purchases.create', 'purchases.read', 'purchases.update',
                'returns.create', 'returns.read', 'returns.update',
                'reports.read', 'reports.generate'
            ],
            'Accountant': [
                'customers.read',
                'suppliers.read',
                'invoices.create', 'invoices.read', 'invoices.update',
                'payments.create', 'payments.read', 'payments.update',
                'purchases.read',
                'reports.read', 'reports.generate'
            ],
            'Stock Manager': [
                'categories.create', 'categories.read', 'categories.update',
                'products.create', 'products.read', 'products.update',
                'purchases.create', 'purchases.read', 'purchases.update',
                'returns.create', 'returns.read', 'returns.update',
                'reports.read'
            ],
            'Sales': [
                'customers.read',
                'products.read',
                'invoices.create', 'invoices.read',
                'payments.read'
            ]
        }
        return permissions.get(role_name, [])

def require_permission(permission_name):
    """Decorator to check permissions before executing a function"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                PermissionService.log_action(
                    None, 'ACCESS_DENIED', permission_name, 
                    success=False, error_message='User not authenticated'
                )
                return {'error': 'Authentication required'}, 401
            
            if not current_user.has_permission(permission_name):
                PermissionService.log_action(
                    current_user.id, 'ACCESS_DENIED', permission_name,
                    success=False, error_message='Insufficient permissions'
                )
                return {'error': 'Insufficient permissions'}, 403
            
            # Log successful access
            PermissionService.log_action(
                current_user.id, 'ACCESS_GRANTED', permission_name
            )
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def log_action(action, resource, resource_id=None):
    """Decorator to log actions"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            try:
                result = f(*args, **kwargs)
                if current_user.is_authenticated:
                    PermissionService.log_action(
                        current_user.id, action, resource, resource_id
                    )
                return result
            except Exception as e:
                if current_user.is_authenticated:
                    PermissionService.log_action(
                        current_user.id, action, resource, resource_id,
                        success=False, error_message=str(e)
                    )
                raise
        return decorated_function
    return decorator