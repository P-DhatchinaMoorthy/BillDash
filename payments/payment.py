from datetime import datetime
from decimal import Decimal
from src.extensions import db
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy import event


class Payment(db.Model):
    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey("invoices.id"), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=False)
    # discount_percentage = db.Column(db.Numeric(5, 2), default=0)
    # discount_amount = db.Column(db.Numeric(14, 2), default=0)
    amount_before_discount = db.Column(db.Numeric(14, 2), nullable=False)
    balance_amount = db.Column(db.Numeric(14, 2), default=0)
    excess_amount = db.Column(db.Numeric(14, 2), default=0)
    payment_date = db.Column(db.DateTime, default=datetime.utcnow)
    payment_method = db.Column(
        db.String(50), nullable=False
    )  # Cash / Card / UPI / Bank Transfer / Cheque
    amount_paid = db.Column(db.Numeric(14, 2), nullable=False)
    bank_details = db.Column(JSON, nullable=True)
    transaction_reference = db.Column(db.String(255), nullable=True)
    payment_status = db.Column(db.String(50), default="Successful")  # Successful / Failed / Pending
    notes = db.Column(db.Text, nullable=True)

    invoice = db.relationship("Invoice", back_populates="payments")
    
    def calculate_amounts(self):
        """Calculate balance amount and payment status based on invoice total"""
        from invoices.invoice import Invoice
        invoice = Invoice.query.get(self.invoice_id)
        if not invoice:
            return
            
        invoice_total = Decimal(invoice.grand_total or 0)
        current_payment = Decimal(self.amount_paid or 0)
        
        # Calculate total of ALL payments for this invoice (including current)
        all_payments = Payment.query.filter_by(invoice_id=self.invoice_id).all()
        total_paid = sum(Decimal(p.amount_paid or 0) for p in all_payments)
        
        # Calculate remaining balance
        remaining_balance = invoice_total - total_paid
        
        if remaining_balance <= 0:
            self.balance_amount = Decimal('0')
            self.excess_amount = abs(remaining_balance)
            self.payment_status = "Successful"
        elif total_paid > 0:
            self.balance_amount = remaining_balance
            self.excess_amount = Decimal('0')
            self.payment_status = "Partially Paid"
        else:
            self.balance_amount = invoice_total
            self.excess_amount = Decimal('0')
            self.payment_status = "Pending"
            
        # Update invoice status
        if remaining_balance <= 0:
            invoice.status = "Paid"
        elif total_paid > 0:
            invoice.status = "Partially Paid"
        else:
            invoice.status = "Pending"

# Event listeners to auto-calculate amounts
@event.listens_for(Payment, "before_insert")
def calculate_payment_before_insert(mapper, connection, target):
    target.calculate_amounts()

@event.listens_for(Payment, "before_update")
def calculate_payment_before_update(mapper, connection, target):
    target.calculate_amounts()
