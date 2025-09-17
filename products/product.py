from datetime import datetime
from decimal import Decimal
from src.extensions import db
from sqlalchemy import event
import uuid

class Product(db.Model):
    __tablename__ = "products"

    # Product ID (Unique Identifier) (Primary key)
    id = db.Column(db.Integer, primary_key=True, autoincrement=False)
    
    # Product Name
    product_name = db.Column(db.String(255), nullable=False)
    
    # Product Description
    description = db.Column(db.Text, nullable=True)
    
    # SKU / Item Code
    sku = db.Column(db.String(100), unique=True, nullable=False)
    
    # Category
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=True)
    
    # Subcategory
    subcategory_id = db.Column(db.Integer, nullable=True)
    
    # Unit of Measure (Piece, Kg, Litre, etc.)
    unit_of_measure = db.Column(db.String(50), nullable=True)
    
    # Unit Price
    selling_price = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    
    # Purchase Price (Cost Price)
    purchase_price = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    
    # Quantity in Stock
    quantity_in_stock = db.Column(db.Integer, default=0, nullable=False)
    
    # Reorder Level (Minimum Stock)
    reorder_level = db.Column(db.Integer, nullable=True)
    
    # Maximum Stock Level
    max_stock_level = db.Column(db.Integer, nullable=True)
    
    # Supplier ID (Linked to Supplier)
    supplier_id = db.Column(db.Integer, db.ForeignKey("suppliers.id"), nullable=True)
    
    # Batch Number (if applicable)
    batch_number = db.Column(db.String(120), nullable=True)
    
    # Expiry Date (if applicable)
    expiry_date = db.Column(db.Date, nullable=True)
    
    # Barcode / QR Code
    barcode = db.Column(db.String(200), nullable=True)

    # Date Added (automate)
    date_added = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Last Updated Date (automate only when updated)
    last_updated = db.Column(db.DateTime, onupdate=datetime.utcnow)