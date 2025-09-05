from flask import request, g
from user.user import AuditLog
from src.extensions import db
from datetime import datetime
import json

def log_user_action(action, module, record_id=None, old_data=None, new_data=None):
    """Enhanced audit logging with JWT user info"""
    try:
        current_user = getattr(g, 'current_user', None)
        if not current_user:
            return
        
        # Get IP and user agent
        ip_address = request.environ.get('HTTP_X_REAL_IP', request.remote_addr)
        user_agent = request.headers.get('User-Agent')
        
        # Create audit log entry
        audit_log = AuditLog(
            user_id=current_user['user_id'],
            action=f"{request.method}_{action}",  # e.g., POST_CREATE_CUSTOMER
            module_name=module,
            record_id=record_id,
            old_data=old_data,
            new_data=new_data,
            ip_address=ip_address,
            user_agent=user_agent,
            timestamp=datetime.utcnow()
        )
        
        db.session.add(audit_log)
        db.session.commit()
        
    except Exception as e:
        db.session.rollback()
        print(f"Audit logging failed: {e}")

def audit_decorator(module, action_type=None):
    """Decorator for automatic audit logging"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Execute the function first
            result = f(*args, **kwargs)
            
            # Log after successful execution
            try:
                # Determine action based on HTTP method if not specified
                if action_type:
                    action = action_type
                else:
                    method_actions = {
                        'POST': 'CREATE',
                        'PUT': 'UPDATE', 
                        'PATCH': 'UPDATE',
                        'DELETE': 'DELETE',
                        'GET': 'READ'
                    }
                    action = method_actions.get(request.method, 'ACTION')
                
                # Extract record ID from kwargs or result
                record_id = kwargs.get('id') or kwargs.get('customer_id') or kwargs.get('user_id')
                
                # Get request data
                request_data = request.get_json() if request.is_json else None
                
                log_user_action(action, module, record_id, None, request_data)
                
            except Exception as e:
                print(f"Audit logging in decorator failed: {e}")
            
            return result
        return decorated_function
    return decorator