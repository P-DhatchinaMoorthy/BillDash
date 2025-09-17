from datetime import datetime
from src.extensions import db
import uuid

class StockTransaction(db.Model):
    __tablename__ = "stock_transactions"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    transaction_type = db.Column(
        db.String(50), nullable=False
    )  # Purchase / Sale / Return / Adjustment / Damage
    sale_type = db.Column(db.String(50), nullable=True)  # With Bill / Without Bill
    quantity = db.Column(db.Integer, nullable=False)
    transaction_date = db.Column(db.DateTime, default=datetime.utcnow)
    supplier_id = db.Column(db.Integer, db.ForeignKey("suppliers.id"), nullable=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey("invoices.id"), nullable=True)
    reference_number = db.Column(db.String(255), nullable=True)
    notes = db.Column(db.Text, nullable=True)

    product = db.relationship("Product", overlaps="product_ref,stock_transactions")
