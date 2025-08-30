from datetime import datetime
from extensions import db
from sqlalchemy.orm import relationship
from sqlalchemy import func
import uuid

class Invoice(db.Model):
    __tablename__ = "invoices"

    id = db.Column(db.Integer, primary_key=True, autoincrement=False)
    invoice_number = db.Column(db.String(100), unique=True, nullable=False)
    
    def __init__(self, **kwargs):
        if 'id' not in kwargs:
            # Get next invoice ID starting from 4001
            last_invoice = Invoice.query.order_by(Invoice.id.desc()).first()
            kwargs['id'] = (last_invoice.id + 1) if last_invoice and last_invoice.id >= 4001 else 4001
        super().__init__(**kwargs)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=False)
    invoice_date = db.Column(db.DateTime, default=datetime.utcnow)
    due_date = db.Column(db.DateTime, nullable=True)
    payment_terms = db.Column(db.String(50), nullable=True)
    currency = db.Column(db.String(10), default="INR")
    total_before_tax = db.Column(db.Numeric(14, 2), default=0)
    tax_amount = db.Column(db.Numeric(14, 2), default=0)
    discount_amount = db.Column(db.Numeric(14, 2), default=0)
    shipping_charges = db.Column(db.Numeric(12, 2), default=0)
    other_charges = db.Column(db.Numeric(12, 2), default=0)
    additional_discount = db.Column(db.Numeric(12, 2), default=0)
    grand_total = db.Column(db.Numeric(14, 2), default=0)
    status = db.Column(db.String(50), default="Pending")  # Pending / Paid / Partially Paid / Cancelled
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    items = relationship("InvoiceItem", back_populates="invoice", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="invoice")
