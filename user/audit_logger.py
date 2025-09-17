from flask import request, g
from user.user import AuditLog, User
from src.extensions import db
from datetime import datetime, date
from functools import wraps
from decimal import Decimal
import json

# Only log these HTTP methods
AUDITED_METHODS = {'POST', 'PUT', 'DELETE'}

def serialize_for_json(obj):
    """Convert objects to JSON-serializable format"""
    if obj is None:
        return None
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, dict):
        return {k: serialize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [serialize_for_json(item) for item in obj]
    return obj

def log_user_action(action, module, record_id=None, old_data=None, new_data=None, resource_name=None, target_user_id=None):
    """Enhanced audit logging - only for POST, PUT, DELETE operations"""
    try:
        # Only log audited methods
        if request.method not in AUDITED_METHODS:
            return
            
        current_user = getattr(g, 'current_user', None)
        if not current_user:
            return
        
        # Get user details from database
        user = User.query.get(current_user['user_id'])
        if not user:
            return
            
        # Get IP and user agent
        ip_address = request.environ.get('HTTP_X_REAL_IP', request.remote_addr)
        user_agent = request.headers.get('User-Agent')
        
        # Serialize data for JSON storage
        serialized_old_data = serialize_for_json(old_data)
        serialized_new_data = serialize_for_json(new_data)
        
        # Create detailed action description with target info
        action_description = f"{request.method}_{action}"
        if resource_name:
            action_description += f"_{resource_name.upper()}"
        if target_user_id and module == 'user_permissions':
            action_description += f"_FOR_USER_{target_user_id}"
        
        # Create audit log entry with enhanced user info
        audit_log = AuditLog(
            user_id=user.id,
            username=user.username,
            user_role=user.role,
            action=action_description,
            module_name=module,
            record_id=record_id or target_user_id,
            old_data=serialized_old_data,
            new_data=serialized_new_data,
            ip_address=ip_address,
            user_agent=user_agent,
            timestamp=datetime.utcnow()
        )
        
        db.session.add(audit_log)
        db.session.commit()
        
    except Exception as e:
        db.session.rollback()
        print(f"Audit logging failed: {e}")

def audit_decorator(module, action_type=None, resource_name=None):
    """Decorator for automatic audit logging - only POST, PUT, DELETE"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Only proceed if method should be audited
            if request.method not in AUDITED_METHODS:
                return f(*args, **kwargs)
            
            # Get old data for UPDATE operations
            old_data = None
            if request.method in ['PUT', 'DELETE']:
                try:
                    # Extract ID from URL path or kwargs
                    record_id = kwargs.get('id') or kwargs.get('customer_id') or kwargs.get('user_id')
                    if record_id and module == 'customers':
                        from customers.customer import Customer
                        existing_record = Customer.query.get(record_id)
                        if existing_record:
                            old_data = {
                                'id': existing_record.id,
                                'contact_person': existing_record.contact_person,
                                'business_name': existing_record.business_name,
                                'phone': existing_record.phone,
                                'email': existing_record.email
                            }
                except Exception:
                    pass
            
            # Execute the function
            result = f(*args, **kwargs)
            
            # Log after successful execution
            try:
                # Determine action based on HTTP method
                if action_type:
                    action = action_type
                else:
                    method_actions = {
                        'POST': 'CREATE',
                        'PUT': 'UPDATE',
                        'DELETE': 'DELETE'
                    }
                    action = method_actions.get(request.method, 'ACTION')
                
                # Extract record ID from kwargs, URL, or response
                record_id = kwargs.get('id') or kwargs.get('customer_id') or kwargs.get('user_id')
                target_user_id = kwargs.get('user_id')  # For user-related operations
                
                # For CREATE operations, try to get ID from response
                if request.method == 'POST' and not record_id:
                    try:
                        if hasattr(result, 'get_json') and result.get_json():
                            response_data = result.get_json()
                            record_id = response_data.get('id')
                    except Exception:
                        pass
                
                # Get request data
                request_data = None
                if request.is_json:
                    request_data = request.get_json()
                elif request.form:
                    request_data = request.form.to_dict()
                
                log_user_action(action, module, record_id, old_data, request_data, resource_name, target_user_id)
                
            except Exception as e:
                print(f"Audit logging in decorator failed: {e}")
            
            return result
        return decorated_function
    return decorator