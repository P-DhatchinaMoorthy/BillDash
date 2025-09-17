from extensions import db
from datetime import datetime
from sqlalchemy import Numeric

class Report(db.Model):
    __tablename__ = 'reports'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    report_name = db.Column(db.String(100), nullable=False)
    generated_by = db.Column(db.String(50), default='Admin')
    date_range_start = db.Column(db.Date, nullable=False)
    date_range_end = db.Column(db.Date, nullable=False)
    total_sales_amount = db.Column(Numeric(15,2), default=0.00)
    total_purchases_amount = db.Column(Numeric(15,2), default=0.00)
    opening_stock_value = db.Column(Numeric(15,2), default=0.00)
    closing_stock_value = db.Column(Numeric(15,2), default=0.00)
    profit_loss_amount = db.Column(Numeric(15,2), default=0.00)
    generated_date = db.Column(db.DateTime, default=datetime.utcnow)
    report_data = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)