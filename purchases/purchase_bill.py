# models/purchase_bill.py
from datetime import datetime
from src.extensions import db
from sqlalchemy.dialects.postgresql import JSON

class PurchaseBill(db.Model):
    __tablename__ = "purchase_bills"

    id = db.Column(db.Integer, primary_key=True)
    bill_number = db.Column(db.String(100), unique=True, nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey("suppliers.id"), nullable=False)
    bill_date = db.Column(db.DateTime, default=datetime.utcnow)
    due_date = db.Column(db.DateTime, nullable=True)
    total_amount = db.Column(db.Numeric(14, 2), nullable=False)
    payment_amount = db.Column(db.Numeric(14, 2), nullable=False)
    payment_method = db.Column(db.String(50), nullable=False)
    payment_status = db.Column(db.String(50), default="Paid")  # Paid / Pending / Failed
    payment_date = db.Column(db.DateTime, default=datetime.utcnow)
    transaction_reference = db.Column(db.String(255), nullable=True)
    bank_details = db.Column(JSON, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    supplier = db.relationship("Supplier", backref="purchase_bills", lazy=True)