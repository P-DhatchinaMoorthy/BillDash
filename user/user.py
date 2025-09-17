from src.extensions import db
from flask_login import UserMixin
from datetime import datetime
from passlib.hash import bcrypt
import json

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    password = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), default='user', nullable=False)
    two_fa_code = db.Column(db.String(6), nullable=True)
    two_fa_expiry = db.Column(db.DateTime, nullable=True)
    last_otp_sent_at = db.Column(db.DateTime, nullable=True)
    phone_number = db.Column(db.String(20), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def check_password(self, password):
        return bcrypt.verify(password, self.password)
    
    def set_password(self, password):
        self.password = bcrypt.hash(password)

class Permission(db.Model):
    __tablename__ = 'permissions'
    id = db.Column(db.Integer, primary_key=True)
    module_name = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class UserPermission(db.Model):
    __tablename__ = 'user_permissions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    permission_id = db.Column(db.Integer, db.ForeignKey('permissions.id'), nullable=False)
    can_read = db.Column(db.Boolean, default=False)
    can_write = db.Column(db.Boolean, default=False)
    can_delete = db.Column(db.Boolean, default=False)
    granted_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    granted_at = db.Column(db.DateTime, default=datetime.utcnow)
    
class AuditLog(db.Model):
    __tablename__ = 'audit_log'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    username = db.Column(db.String(80), nullable=False)
    user_role = db.Column(db.String(20), nullable=False)
    action = db.Column(db.String(50), nullable=False)
    module_name = db.Column(db.String(50), nullable=False)
    record_id = db.Column(db.Integer)
    old_data = db.Column(db.JSON)
    new_data = db.Column(db.JSON)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship to user
    user = db.relationship('User', backref='audit_logs')