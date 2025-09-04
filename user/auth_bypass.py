from functools import wraps

def require_permission(module, action=None):
    """Bypass version - allows all requests for testing"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Simply execute the function without permission checks
            return f(*args, **kwargs)
        return decorated_function
    return decorator