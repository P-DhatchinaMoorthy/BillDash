from functools import wraps
from flask import request, jsonify, g
from user.jwt_utils import decode_jwt_token, get_token_from_header
from user.user import User

def jwt_required(f):
    """JWT authentication decorator"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = get_token_from_header(request)
        if not token:
            return jsonify({'error': 'Token missing'}), 401
        
        payload = decode_jwt_token(token)
        if not payload:
            return jsonify({'error': 'Invalid or expired token'}), 401
        
        # Store user info in g for use in routes
        g.current_user = {
            'user_id': payload['user_id'],
            'username': payload['username'],
            'role': payload['role']
        }
        
        return f(*args, **kwargs)
    return decorated_function

def get_current_user():
    """Get current user from JWT token"""
    return getattr(g, 'current_user', None)