from datetime import datetime
from src.extensions import db
from sqlalchemy.orm import relationship

class SupplierDamage(db.Model):
    __tablename__ = "supplier_damages"

    id = db.Column(db.Integer, primary_key=True)
    damage_number = db.Column(db.String(100), unique=True, nullable=False)
    
    # Purchase reference
    purchase_id = db.Column(db.Integer, db.ForeignKey("stock_transactions.id"), nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey("suppliers.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    
    # Damage details
    quantity_damaged = db.Column(db.Integer, nullable=False)
    damage_type = db.Column(db.String(20), nullable=False)  # 'refund', 'replacement'
    damage_reason = db.Column(db.String(255), nullable=True)
    damage_date = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Financial details
    unit_price = db.Column(db.Numeric(12, 2), nullable=False)
    total_amount = db.Column(db.Numeric(12, 2), nullable=False)
    
    # Status tracking
    status = db.Column(db.String(20), default="Pending")  # Pending, Approved, Rejected, Completed
    supplier_response = db.Column(db.String(50), nullable=True)  # Accepted, Rejected, Partial
    
    # Resolution details
    refund_amount = db.Column(db.Numeric(12, 2), default=0)
    replacement_quantity = db.Column(db.Integer, default=0)
    replacement_date = db.Column(db.DateTime, nullable=True)
    
    # Notes and tracking
    notes = db.Column(db.Text, nullable=True)
    created_by = db.Column(db.String(100), nullable=True)
    resolved_by = db.Column(db.String(100), nullable=True)
    resolved_date = db.Column(db.DateTime, nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    # Relationships
    purchase = relationship("StockTransaction", foreign_keys=[purchase_id])
    supplier = relationship("Supplier", foreign_keys=[supplier_id])
    product = relationship("Product", foreign_keys=[product_id])

    def __init__(self, **kwargs):
        if 'damage_number' not in kwargs:
            date_str = datetime.now().strftime("%Y%m%d")
            last_damage = SupplierDamage.query.filter(
                SupplierDamage.damage_number.like(f"DMG-{date_str}-%")
            ).order_by(SupplierDamage.id.desc()).first()
            
            if last_damage:
                last_num = int(last_damage.damage_number.split('-')[-1])
                new_num = last_num + 1
            else:
                new_num = 1
            
            kwargs['damage_number'] = f"DMG-{date_str}-{new_num:04d}"
        
        # Calculate total amount
        if 'total_amount' not in kwargs and 'unit_price' in kwargs and 'quantity_damaged' in kwargs:
            kwargs['total_amount'] = kwargs['unit_price'] * kwargs['quantity_damaged']
        
        super().__init__(**kwargs)