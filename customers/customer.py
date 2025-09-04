from datetime import datetime
from src.extensions import db
import pandas as pd

class Customer(db.Model):
    __tablename__ = "customers"

    # Customer ID (Unique Identifier)
    id = db.Column(db.Integer, primary_key=True, autoincrement=False)
    
    def __init__(self, **kwargs):
        if 'id' not in kwargs:
            # Get next customer ID starting from 8001
            last_customer = Customer.query.order_by(Customer.id.desc()).first()
            kwargs['id'] = (last_customer.id + 1) if last_customer and last_customer.id >= 8001 else 8001
        super().__init__(**kwargs)
    
    # Contact Person / Full Name
    contact_person = db.Column(db.String(255), nullable=False)
    business_name = db.Column(db.String(255), nullable=True)
    
    # Email Address
    email = db.Column(db.String(255), nullable=True)
    
    # Phone Number (Primary key)
    phone = db.Column(db.String(50), unique=True, nullable=False)
    
    # Alternate Phone Number
    alternate_phone = db.Column(db.String(50), nullable=True)
    
    # Billing Address
    billing_address = db.Column(db.Text, nullable=True)
    
    # Shipping Address
    shipping_address = db.Column(db.Text, nullable=True)
    
    # GST / Tax Number
    gst_number = db.Column(db.String(50), nullable=True)

    # Branch
    branch = db.Column(db.String(100), nullable=True)

    # Documents Type (e.g., GSTIN, PAN, etc.)
    documents = db.Column(db.String(500), nullable=True)

    # PAN Number (if applicable)
    pan_number = db.Column(db.String(50), nullable=True)
    
    # Payment Terms (e.g., Net 15, Net 30)
    payment_terms = db.Column(db.String(50), nullable=True)
    
    # Opening Balance
    opening_balance = db.Column(db.Numeric(12, 2), default=0)
    
    # Notes / Special Instructions
    notes = db.Column(db.Text, nullable=True)
    
    # Created Date (automate)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Last Updated Date (automate only when updated)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    invoices = db.relationship("Invoice", backref="customer", lazy=True)
    payments = db.relationship("Payment", backref="customer", lazy=True)
    
    @classmethod
    def bulk_import(cls, df):
        results = []
        success_count = 0
        
        for index, row in df.iterrows():
            try:
                # Convert phone to string first to avoid type casting issues
                phone_value = row['phone']
                if pd.notna(phone_value):
                    phone_str = str(int(phone_value)) if isinstance(phone_value, (int, float)) else str(phone_value)
                else:
                    phone_str = ""
                
                if cls.query.filter_by(phone=phone_str).first():
                    results.append({
                        "row": index + 1,
                        "status": "error",
                        "error": "Phone number already exists"
                    })
                    continue
                
                customer_data = {
                    'contact_person': str(row['contact_person']),
                    'phone': phone_str
                }
                
                for field in ['business_name', 'email', 'alternate_phone', 'billing_address', 
                             'shipping_address', 'gst_number', 'branch', 'pan_number', 
                             'payment_terms', 'notes', 'documents']:
                    if field in row and pd.notna(row[field]):
                        customer_data[field] = str(row[field])
                
                if 'opening_balance' in row and pd.notna(row['opening_balance']):
                    customer_data['opening_balance'] = float(row['opening_balance'])
                
                customer = cls(**customer_data)
                db.session.add(customer)
                db.session.commit()
                
                results.append({
                    "row": index + 1,
                    "status": "success",
                    "customer_id": customer.id,
                    "contact_person": customer.contact_person,
                    "phone": customer.phone
                })
                success_count += 1
                
            except Exception as e:
                db.session.rollback()
                results.append({
                    "row": index + 1,
                    "status": "error",
                    "error": str(e)
                })
        
        return results, success_count
