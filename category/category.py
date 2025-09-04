from datetime import datetime
from src.extensions import db
from decimal import Decimal

class Category(db.Model):
    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True, autoincrement=False)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    subcategory_id = db.Column(db.Integer, nullable=True)
    subcategory_name = db.Column(db.String(255), nullable=True)
    hsn_code = db.Column(db.String(20), nullable=True)
    cgst_rate = db.Column(db.Numeric(5, 2), nullable=False, default=0)
    sgst_rate = db.Column(db.Numeric(5, 2), nullable=False, default=0)
    igst_rate = db.Column(db.Numeric(5, 2), nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # products = db.relationship("Product", backref="category", lazy=True)  # Removed to avoid circular import

class SubCategory(db.Model):
    __tablename__ = "subcategories"

    id = db.Column(db.Integer, primary_key=True, autoincrement=False)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
