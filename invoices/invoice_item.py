from src.extensions import db
from sqlalchemy.orm import relationship
import uuid

class InvoiceItem(db.Model):
    __tablename__ = "invoice_items"

    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey("invoices.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    unit_price = db.Column(db.Numeric(12, 2), nullable=False)  # fetched from product.selling_price
    discount_per_item = db.Column(db.Numeric(12, 2), default=0)
    discount_type = db.Column(db.String(10), default='percentage')  # 'percentage' or 'amount'
    tax_rate_per_item = db.Column(db.Numeric(5, 2), default=0)  # percentage (IGST rate)
    cgst_rate = db.Column(db.Numeric(5, 2), default=0)  # percentage
    sgst_rate = db.Column(db.Numeric(5, 2), default=0)  # percentage
    igst_rate = db.Column(db.Numeric(5, 2), default=0)  # percentage
    cgst_amount = db.Column(db.Numeric(12, 2), default=0)
    sgst_amount = db.Column(db.Numeric(12, 2), default=0)
    igst_amount = db.Column(db.Numeric(12, 2), default=0)
    total_price = db.Column(db.Numeric(14, 2), nullable=False)

    invoice = relationship("Invoice", back_populates="items")
    product = relationship("Product", overlaps="invoice_items,product_ref")
