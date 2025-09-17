import jwt
from datetime import datetime, timedelta
from flask import current_app
import os
import secrets

# JWT Configuration
JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'your-secret-key-change-in-production')
REFRESH_SECRET_KEY = os.environ.get('REFRESH_SECRET_KEY', 'your-refresh-secret-key-change-in-production')
JWT_ALGORITHM = 'HS256'

# Token Validity Periods
ACCESS_TOKEN_EXPIRATION_DAYS = 1     # Access token for 1 day
REFRESH_TOKEN_EXPIRATION_DAYS = 7     # Longer-lived refresh token

def generate_tokens(user):
    """Generate both access and refresh tokens for user"""
    now = datetime.utcnow()
    
    # Access Token (1 day)
    access_payload = {
        'user_id': user.id,
        'username': user.username,
        'role': user.role,
        'token_type': 'access',
        'exp': now + timedelta(days=ACCESS_TOKEN_EXPIRATION_DAYS),
        'iat': now,
        'jti': secrets.token_hex(16)  # Unique token ID
    }
    access_token = jwt.encode(access_payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    
    # Refresh Token (long-lived)
    refresh_payload = {
        'user_id': user.id,
        'username': user.username,
        'token_type': 'refresh',
        'exp': now + timedelta(days=REFRESH_TOKEN_EXPIRATION_DAYS),
        'iat': now,
        'jti': secrets.token_hex(16)  # Unique token ID
    }
    refresh_token = jwt.encode(refresh_payload, REFRESH_SECRET_KEY, algorithm=JWT_ALGORITHM)
    
    return {
        'access_token': access_token,
        'refresh_token': refresh_token,
        'access_expires_in': ACCESS_TOKEN_EXPIRATION_DAYS * 24 * 60 * 60,  # seconds
        'refresh_expires_in': REFRESH_TOKEN_EXPIRATION_DAYS * 24 * 60 * 60,  # seconds
        'token_type': 'Bearer'
    }

def generate_jwt_token(user):
    """Legacy function - generates access token only"""
    return generate_tokens(user)['access_token']

def decode_access_token(token):
    """Decode and validate access token"""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        if payload.get('token_type') != 'access':
            return None
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

def decode_refresh_token(token):
    """Decode and validate refresh token"""
    try:
        payload = jwt.decode(token, REFRESH_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        if payload.get('token_type') != 'refresh':
            return None
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

def decode_jwt_token(token):
    """Legacy function - decodes access token"""
    return decode_access_token(token)

def refresh_access_token(refresh_token):
    """Generate new access token using refresh token"""
    payload = decode_refresh_token(refresh_token)
    if not payload:
        return None
    
    from user.user import User
    user = User.query.get(payload['user_id'])
    if not user:
        return None
    
    # Generate new access token
    now = datetime.utcnow()
    access_payload = {
        'user_id': user.id,
        'username': user.username,
        'role': user.role,
        'token_type': 'access',
        'exp': now + timedelta(days=ACCESS_TOKEN_EXPIRATION_DAYS),
        'iat': now,
        'jti': secrets.token_hex(16)
    }
    
    return {
        'access_token': jwt.encode(access_payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM),
        'expires_in': ACCESS_TOKEN_EXPIRATION_DAYS * 24 * 60 * 60,
        'token_type': 'Bearer'
    }

def get_token_from_header(request):
    """Extract token from Authorization header"""
    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        return auth_header.split(' ')[1]
    return None