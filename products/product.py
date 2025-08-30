from datetime import datetime
from decimal import Decimal
from extensions import db
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

    # Relationships
    invoice_items = db.relationship("InvoiceItem", backref="product_ref", lazy=True)
    sales_no_invoice = db.relationship("SaleNoInvoice", backref="product_ref", lazy=True)
    stock_transactions = db.relationship("StockTransaction", backref="product_ref", lazy=True)

    # auto-calc selling price: purchase_price * 1.10
    def compute_selling_price(self):
        # using Decimal for precise monetary calculation
        pp = Decimal(self.purchase_price or 0)
        sp = (pp * Decimal("1.10")).quantize(Decimal("0.01"))
        return sp

# event listeners to auto-set selling_price when insert or update
@event.listens_for(Product, "before_insert")
def set_selling_price_before_insert(mapper, connection, target):
    if target.purchase_price is not None:
        target.selling_price = target.compute_selling_price()

@event.listens_for(Product, "before_update")
def set_selling_price_before_update(mapper, connection, target):
    # Recompute selling price if purchase_price changed
    target.selling_price = target.compute_selling_price()
