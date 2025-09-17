from datetime import datetime
from src.extensions import db

class SaleNoInvoice(db.Model):
    __tablename__ = "sales_no_invoice"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    selling_price = db.Column(db.Numeric(12,2), nullable=False)
    total_amount = db.Column(db.Numeric(14,2), nullable=False)
    sale_date = db.Column(db.DateTime, default=datetime.utcnow)
    discount_percentage = db.Column(db.Numeric(5,2), default=0)
    discount_amount = db.Column(db.Numeric(14,2), default=0)
    amount_after_discount = db.Column(db.Numeric(14,2), nullable=False)
    payment_method = db.Column(db.String(50), nullable=False)
    notes = db.Column(db.Text, nullable=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=False)

    product = db.relationship("Product", overlaps="product_ref,sales_no_invoice")
