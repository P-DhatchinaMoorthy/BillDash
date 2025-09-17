from datetime import datetime
from src.extensions import db
from sqlalchemy.orm import relationship

class ProductReturn(db.Model):
    __tablename__ = "product_returns"

    id = db.Column(db.Integer, primary_key=True, autoincrement=False)
    return_number = db.Column(db.String(100), unique=True, nullable=False)
    
    # Original sale reference
    original_invoice_id = db.Column(db.Integer, db.ForeignKey("invoices.id"), nullable=True)
    original_sale_no_invoice_id = db.Column(db.Integer, db.ForeignKey("sales_no_invoice.id"), nullable=True)
    
    # Customer and product details
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    
    # Return details
    return_type = db.Column(db.String(20), nullable=False)  # 'return', 'exchange', 'damage'
    quantity_returned = db.Column(db.Integer, nullable=False)
    return_date = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Financial details
    original_price = db.Column(db.Numeric(12, 2), nullable=False)
    refund_amount = db.Column(db.Numeric(12, 2), default=0)
    
    # Exchange details (if applicable)
    exchange_product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=True)
    exchange_quantity = db.Column(db.Integer, default=0)
    exchange_price_difference = db.Column(db.Numeric(12, 2), default=0)
    
    # Status and processing
    status = db.Column(db.String(20), default="Pending")  # Pending, Processed, Completed
    reason = db.Column(db.String(255), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    
    # Damage specific fields
    damage_level = db.Column(db.String(20), nullable=True)  # 'Minor', 'Major', 'Total'
    is_resaleable = db.Column(db.Boolean, default=False)
    product_type = db.Column(db.String(20), nullable=True)  # 'refund', 'replacement' for damage returns
    
    # Processing details
    processed_by = db.Column(db.String(100), nullable=True)
    processed_date = db.Column(db.DateTime, nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    # Relationships
    customer = relationship("Customer")
    product = relationship("Product", foreign_keys=[product_id])
    exchange_product = relationship("Product", foreign_keys=[exchange_product_id])
    original_invoice = relationship("Invoice")
    original_sale_no_invoice = relationship("SaleNoInvoice")

    def __init__(self, **kwargs):
        if 'id' not in kwargs:
            # Get next return ID starting from 9001
            last_return = ProductReturn.query.order_by(ProductReturn.id.desc()).first()
            kwargs['id'] = (last_return.id + 1) if last_return and last_return.id >= 9001 else 9001
        
        if 'return_number' not in kwargs:
            # Generate return number: RET-YYYYMMDD-XXXX
            from datetime import datetime
            date_str = datetime.now().strftime("%Y%m%d")
            last_return = ProductReturn.query.filter(
                ProductReturn.return_number.like(f"RET-{date_str}-%")
            ).order_by(ProductReturn.id.desc()).first()
            
            if last_return:
                last_num = int(last_return.return_number.split('-')[-1])
                new_num = last_num + 1
            else:
                new_num = 1
            
            kwargs['return_number'] = f"RET-{date_str}-{new_num:04d}"
        
        super().__init__(**kwargs)

class DamagedProduct(db.Model):
    __tablename__ = "damaged_products"

    id = db.Column(db.Integer, primary_key=True, autoincrement=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    return_id = db.Column(db.Integer, db.ForeignKey("product_returns.id"), nullable=True)
    
    quantity = db.Column(db.Integer, nullable=False)
    damage_date = db.Column(db.DateTime, default=datetime.utcnow)
    damage_reason = db.Column(db.String(255), nullable=True)
    damage_level = db.Column(db.String(20), nullable=False)  # 'Minor', 'Major', 'Total'
    
    # Storage location for damaged items
    storage_location = db.Column(db.String(100), nullable=True)
    
    # Disposal/repair tracking
    action_taken = db.Column(db.String(50), nullable=True)  # 'Repair', 'Dispose', 'Return_to_Supplier'
    action_date = db.Column(db.DateTime, nullable=True)
    repair_cost = db.Column(db.Numeric(12, 2), default=0)
    
    # Status
    status = db.Column(db.String(20), default="Stored")  # Stored, Repaired, Disposed, Returned
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    # Relationships
    product = relationship("Product")
    return_record = relationship("ProductReturn")

    def __init__(self, **kwargs):
        if 'id' not in kwargs:
            # Get next damaged product ID starting from 6001
            last_damaged = DamagedProduct.query.order_by(DamagedProduct.id.desc()).first()
            kwargs['id'] = (last_damaged.id + 1) if last_damaged and last_damaged.id >= 6001 else 6006
        
        super().__init__(**kwargs)