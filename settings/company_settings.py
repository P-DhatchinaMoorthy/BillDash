from datetime import datetime
from src.extensions import db

class Settings(db.Model):
    __tablename__ = "settings"
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Business Information
    business_name = db.Column(db.String(255), nullable=True)
    business_type = db.Column(db.String(100), nullable=True)
    registration_number = db.Column(db.String(100), nullable=True)
    gst_number = db.Column(db.String(50), nullable=True)
    pan_number = db.Column(db.String(50), nullable=True)
    
    # Logo & Branding
    logo_path = db.Column(db.String(500), nullable=True)
    tagline = db.Column(db.String(255), nullable=True)
    
    # Contact Details
    primary_phone = db.Column(db.String(50), nullable=True)
    secondary_phone = db.Column(db.String(50), nullable=True)
    primary_email = db.Column(db.String(255), nullable=True)
    secondary_email = db.Column(db.String(255), nullable=True)
    website = db.Column(db.String(255), nullable=True)
    
    # Address Information
    registered_address = db.Column(db.Text, nullable=True)
    billing_address = db.Column(db.Text, nullable=True)
    shipping_address = db.Column(db.Text, nullable=True)
    city = db.Column(db.String(100), nullable=True)
    state = db.Column(db.String(100), nullable=True)
    postal_code = db.Column(db.String(20), nullable=True)
    country = db.Column(db.String(100), nullable=True)
    
    # Bank Details
    bank_name = db.Column(db.String(255), nullable=True)
    account_number = db.Column(db.String(50), nullable=True)
    ifsc_code = db.Column(db.String(20), nullable=True)
    branch = db.Column(db.String(255), nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)