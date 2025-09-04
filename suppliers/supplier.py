from datetime import datetime
from src.extensions import db
from sqlalchemy.dialects.postgresql import JSON
import uuid

class Supplier(db.Model):
    __tablename__ = "suppliers"

    # Supplier ID (Primary key)
    id = db.Column(db.Integer, primary_key=True, autoincrement=False)
    
    def __init__(self, **kwargs):
        if 'id' not in kwargs:
            # Get next supplier ID starting from 6001
            last_supplier = Supplier.query.order_by(Supplier.id.desc()).first()
            kwargs['id'] = (last_supplier.id + 1) if last_supplier and last_supplier.id >= 6001 else 6001
        super().__init__(**kwargs)
    
    # Supplier Name / Business Name
    name = db.Column(db.String(255), nullable=False)
    
    # Contact Person
    contact_person = db.Column(db.String(255), nullable=True)
    
    # Email Address
    email = db.Column(db.String(255), nullable=True)
    
    # Phone Number (Primary key)
    phone = db.Column(db.String(50), nullable=False)
    
    # Alternate Phone Number
    alternate_phone = db.Column(db.String(50), nullable=True)
    
    # Address
    address = db.Column(db.Text, nullable=True)
    
    # GST / Tax Number
    gst_number = db.Column(db.String(50), nullable=True)
    
    # Bank Details (Account No., IFSC, etc.)
    bank_details = db.Column(JSON, nullable=True)
    
    # Payment Terms
    payment_terms = db.Column(db.String(50), nullable=True)
    
    # Notes / Remarks
    notes = db.Column(db.Text, nullable=True)
    
    # Created Date (automate)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Last Updated Date (automate only when updated)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    # Relationships
    products = db.relationship("Product", backref="supplier_ref", lazy=True)
    stock_transactions = db.relationship("StockTransaction", backref="supplier_ref", lazy=True)
