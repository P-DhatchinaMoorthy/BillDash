from datetime import datetime
from src.extensions import db
from sqlalchemy.orm import relationship

class SupplierReturn(db.Model):
    __tablename__ = "supplier_returns"

    id = db.Column(db.Integer, primary_key=True)
    return_number = db.Column(db.String(100), unique=True, nullable=False)
    
    # Reference to damaged product
    damaged_product_id = db.Column(db.Integer, db.ForeignKey("damaged_products.id"), nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey("suppliers.id"), nullable=False)
    
    # Return details
    return_type = db.Column(db.String(20), nullable=False)  # 'refund', 'replacement'
    quantity_returned = db.Column(db.Integer, nullable=False)
    return_date = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Financial details
    refund_amount = db.Column(db.Numeric(12, 2), default=0)
    
    # Status
    status = db.Column(db.String(20), default="Sent")  # Sent, Acknowledged, Completed
    notes = db.Column(db.Text, nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    # Relationships
    damaged_product = relationship("DamagedProduct")
    supplier = relationship("Supplier")

    def __init__(self, **kwargs):
        if 'return_number' not in kwargs:
            date_str = datetime.now().strftime("%Y%m%d")
            last_return = SupplierReturn.query.filter(
                SupplierReturn.return_number.like(f"SR-{date_str}-%")
            ).order_by(SupplierReturn.id.desc()).first()
            
            if last_return:
                last_num = int(last_return.return_number.split('-')[-1])
                new_num = last_num + 1
            else:
                new_num = 1
            
            kwargs['return_number'] = f"SR-{date_str}-{new_num:04d}"
        
        super().__init__(**kwargs)