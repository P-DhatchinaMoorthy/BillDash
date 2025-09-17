from src.extensions import db
from datetime import datetime

class PasswordResetToken(db.Model):
    __tablename__ = 'password_reset_tokens'
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    expiry_date = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)