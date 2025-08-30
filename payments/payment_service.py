from decimal import Decimal
from extensions import db
from payments.payment import Payment
from invoices.invoice import Invoice
from customers.customer import Customer
from datetime import datetime

class PaymentService:
    @staticmethod
    def create_payment(invoice_id, amount, method, discount_percentage=0, bank_details=None, transaction_reference=None, notes=None):
        """
        Create payment for an invoice with automatic customer detection.
        """
        invoice = Invoice.query.get(invoice_id)
        if not invoice:
            raise ValueError("Invoice not found")
        
        customer_id = invoice.customer_id
        payment = PaymentService.make_payment(
            invoice_id=invoice_id,
            customer_id=customer_id,
            amount=amount,
            method=method,
            discount_percentage=discount_percentage,
            bank_details=bank_details,
            transaction_reference=transaction_reference
        )
        
        # Add notes if provided
        if notes:
            payment.notes = notes
            db.session.commit()
        
        return {
            "payment_id": payment.id,
            "invoice_id": payment.invoice_id,
            "customer_id": payment.customer_id,
            "payment_details": {
                "amount_before_discount": f"{payment.amount_before_discount:.2f}",
                "discount_percentage": f"{payment.discount_percentage:.2f}",
                "discount_amount": f"{payment.discount_amount:.2f}",
                "amount_paid": f"{payment.amount_paid:.2f}",
                "balance_amount": f"{max(Decimal('0'), payment.balance_amount):.2f}",
                "excess_amount": f"{payment.excess_amount:.2f}",
                "payment_method": payment.payment_method,
                "payment_status": payment.payment_status,
                "transaction_reference": payment.transaction_reference
            },
            "invoice_status": invoice.status
        }
    
    @staticmethod
    def make_payment(invoice_id, customer_id, amount, method, discount_percentage=0, bank_details=None, transaction_reference=None):
        """
        Enhanced payment processing with detailed tracking.
        """
        invoice = Invoice.query.get(invoice_id)
        if not invoice:
            raise ValueError("Invoice not found")
        
        customer = Customer.query.get(customer_id)
        if not customer:
            raise ValueError("Customer not found")
        
        if invoice.customer_id != customer_id:
            raise ValueError("Customer does not match invoice")

        # Calculate amounts
        invoice_total = Decimal(invoice.grand_total or 0)
        amount_before_discount = Decimal(amount)
        discount_pct = Decimal(discount_percentage or 0)
        discount_amount = (amount_before_discount * discount_pct / Decimal("100.00")).quantize(Decimal("0.01"))
        amount_after_discount = amount_before_discount - discount_amount
        
        # Calculate previous payments
        previous_payments = sum([Decimal(p.amount_paid) for p in invoice.payments])
        remaining_balance = invoice_total - previous_payments
        
        # Calculate balance and excess
        if amount_after_discount >= remaining_balance:
            balance_amount = Decimal("0.00")
            excess_amount = amount_after_discount - remaining_balance
        else:
            balance_amount = remaining_balance - amount_after_discount
            excess_amount = Decimal("0.00")

        payment = Payment(
            invoice_id=invoice.id,
            customer_id=customer.id,
            payment_date=datetime.utcnow(),
            payment_method=method,
            amount_before_discount=amount_before_discount,
            discount_percentage=discount_pct,
            discount_amount=discount_amount,
            amount_paid=amount_after_discount,
            balance_amount=balance_amount,
            excess_amount=excess_amount,
            bank_details=bank_details,
            transaction_reference=transaction_reference,
            payment_status="Successful",
        )
        db.session.add(payment)

        # Update invoice status
        total_paid = previous_payments + amount_after_discount
        if total_paid >= invoice_total:
            invoice.status = "Paid"
        else:
            invoice.status = "Partially Paid"

        db.session.commit()
        return payment
    
    @staticmethod
    def can_edit_payment(payment_id):
        """
        Check if payment can be edited (pending or partial).
        """
        payment = Payment.query.get(payment_id)
        if not payment:
            return False
        
        invoice = Invoice.query.get(payment.invoice_id)
        return invoice.status in ["Pending", "Partially Paid"]
    
    @staticmethod
    def update_payment(payment_id, amount=None, method=None, discount_percentage=None, bank_details=None, transaction_reference=None):
        """
        Update payment if status allows editing.
        """
        payment = Payment.query.get(payment_id)
        if not payment:
            raise ValueError("Payment not found")
        
        invoice = Invoice.query.get(payment.invoice_id)
        if invoice.status not in ["Pending", "Partially Paid"]:
            raise ValueError("Cannot edit payment - invoice is fully paid")
        
        if amount is not None:
            # Create a new payment record for additional amount instead of updating existing
            additional_amount = Decimal(amount)
            discount_pct = Decimal(discount_percentage or 0)
            discount_amount = (additional_amount * discount_pct / Decimal('100')).quantize(Decimal('0.01'))
            additional_after_discount = additional_amount - discount_amount
            
            # Create new payment record
            new_payment = Payment(
                invoice_id=invoice.id,
                customer_id=payment.customer_id,
                payment_date=datetime.utcnow(),
                payment_method=method or payment.payment_method,
                amount_before_discount=additional_amount,
                discount_percentage=discount_pct,
                discount_amount=discount_amount,
                amount_paid=additional_after_discount,
                bank_details=bank_details or payment.bank_details,
                transaction_reference=transaction_reference or payment.transaction_reference,
                payment_status="Successful"
            )
            db.session.add(new_payment)
            
            # Calculate total payments including new one
            all_payments = sum([Decimal(p.amount_paid) for p in invoice.payments]) + additional_after_discount
            
            # Update invoice status and balance
            if all_payments >= Decimal(invoice.grand_total):
                balance_amount = Decimal('0')
                excess_amount = all_payments - Decimal(invoice.grand_total)
                invoice.status = "Paid"
            else:
                balance_amount = Decimal(invoice.grand_total) - all_payments
                excess_amount = Decimal('0')
                invoice.status = "Partially Paid"
            
            # Update new payment with calculated values
            new_payment.balance_amount = balance_amount
            new_payment.excess_amount = excess_amount
            
            # Return the new payment instead of updated original
            payment = new_payment
        
        if method:
            payment.payment_method = method
        if bank_details:
            payment.bank_details = bank_details
        if transaction_reference:
            payment.transaction_reference = transaction_reference
        
        db.session.commit()
        return payment
    
    @staticmethod
    def get_detailed_invoice(invoice_id):
        """
        Get comprehensive invoice details with ALL information.
        """
        invoice = Invoice.query.get(invoice_id)
        if not invoice:
            return None
        
        customer = Customer.query.get(invoice.customer_id)
        payments = Payment.query.filter_by(invoice_id=invoice_id).all()
        
        # Calculate totals
        total_paid = sum([Decimal(p.amount_paid) for p in payments])
        total_discount = sum([Decimal(p.discount_amount) for p in payments])
        total_excess = sum([Decimal(p.excess_amount) for p in payments])
        balance_due = Decimal(invoice.grand_total) - total_paid
        
        return {
            "invoice": {
                "id": invoice.id,
                "invoice_number": f"INV-{invoice.id}",
                "invoice_date": invoice.invoice_date.isoformat(),
                "due_date": invoice.due_date.isoformat() if invoice.due_date else None,
                "payment_terms": invoice.payment_terms,
                "currency": invoice.currency,
                "status": invoice.status,
                "total_before_tax": str(invoice.total_before_tax),
                "tax_amount": str(invoice.tax_amount),
                "discount_amount": str(invoice.discount_amount),
                "shipping_charges": str(invoice.shipping_charges),
                "other_charges": str(invoice.other_charges),
                "grand_total": str(invoice.grand_total),
                "notes": invoice.notes,
                "created_at": invoice.created_at.isoformat(),
                "updated_at": invoice.updated_at.isoformat() if invoice.updated_at else None
            },
            "customer": {
                "id": customer.id,
                "full_name": customer.contact_person,
                "business_name": customer.business_name,
                "contact_person": customer.contact_person,
                "email": customer.email,
                "phone": customer.phone,
                "alternate_phone": customer.alternate_phone,
                "billing_address": customer.billing_address,
                "shipping_address": customer.shipping_address,
                "gst_number": customer.gst_number,
                "pan_number": customer.pan_number,
                "payment_terms": customer.payment_terms,
                "opening_balance": str(customer.opening_balance),
                "notes": customer.notes,
                "created_at": customer.created_at.isoformat(),
                "updated_at": customer.updated_at.isoformat() if customer.updated_at else None
            },
            "items": [{
                "id": item.id,
                "product_id": item.product_id,
                "product_name": item.product.product_name,
                "sku": item.product.sku,
                "description": item.product.description,
                "category": item.product.category.name if item.product.category else None,
                "category_id": item.product.category_id,
                "subcategory": item.product.category.subcategory_name if item.product.category else None,
                "subcategory_id": item.product.subcategory_id,
                "unit_of_measure": item.product.unit_of_measure,
                "barcode": item.product.barcode,
                "batch_number": item.product.batch_number,
                "expiry_date": item.product.expiry_date.isoformat() if item.product.expiry_date else None,
                "quantity": item.quantity,
                "unit_price": str(item.unit_price),
                "discount_per_item": str(item.discount_per_item),
                "tax_rate_per_item": str(item.tax_rate_per_item),
                "total_price": str(item.total_price),
                "supplier_info": {
                    "supplier_name": item.product.supplier_ref.name if item.product.supplier_ref else None,
                    "supplier_phone": item.product.supplier_ref.phone if item.product.supplier_ref else None
                } if item.product.supplier_id else None
            } for item in invoice.items],
            "payments": [{
                "id": p.id,
                "payment_date": p.payment_date.isoformat(),
                "payment_method": p.payment_method,
                "amount_before_discount": f"{p.amount_before_discount:.2f}",
                "discount_percentage": f"{p.discount_percentage:.2f}",
                "discount_amount": f"{p.discount_amount:.2f}",
                "amount_paid": f"{p.amount_paid:.2f}",
                "balance_amount": f"{max(Decimal('0'), p.balance_amount):.2f}",
                "excess_amount": f"{p.excess_amount:.2f}",
                "transaction_reference": p.transaction_reference,
                "payment_status": p.payment_status,
                "bank_details": p.bank_details,
                "notes": p.notes
            } for p in payments],
            "summary": {
                "invoice_total": f"{invoice.grand_total:.2f}",
                "total_amount_paid": f"{total_paid:.2f}",
                "total_discount_given": f"{total_discount:.2f}",
                "total_excess_amount": f"{total_excess:.2f}",
                "balance_due": f"{max(Decimal('0'), balance_due):.2f}",
                "amount_to_return": f"{total_excess:.2f}" if total_excess > 0 else "0.00",
                "payment_status": invoice.status,
                "number_of_payments": len(payments),
                "last_payment_date": payments[-1].payment_date.isoformat() if payments else None
            },
            "calculations": {
                "subtotal": f"{invoice.total_before_tax:.2f}",
                "tax_amount": f"{invoice.tax_amount:.2f}",
                "invoice_discount": f"{invoice.discount_amount:.2f}",
                "shipping_charges": f"{invoice.shipping_charges:.2f}",
                "other_charges": f"{invoice.other_charges:.2f}",
                "grand_total": f"{invoice.grand_total:.2f}",
                "total_paid": f"{total_paid:.2f}",
                "payment_discounts": f"{total_discount:.2f}",
                "net_amount_received": f"{(total_paid - total_excess):.2f}",
                "excess_to_return": f"{total_excess:.2f}",
                "outstanding_balance": f"{max(Decimal('0'), balance_due):.2f}"
            }
        }
    
    @staticmethod
    def get_outstanding_summary():
        """Get summary of all outstanding payments"""
        from invoices.invoice import Invoice
        from customers.customer import Customer
        
        outstanding_invoices = Invoice.query.filter(
            Invoice.status.in_(['Pending', 'Partially Paid'])
        ).all()
        
        total_outstanding = Decimal('0')
        overdue_amount = Decimal('0')
        
        for invoice in outstanding_invoices:
            total_paid = sum(Decimal(p.amount_paid or 0) for p in invoice.payments)
            outstanding = Decimal(invoice.grand_total) - total_paid
            
            if outstanding > 0:
                total_outstanding += outstanding
                
                if invoice.due_date and datetime.now() > invoice.due_date:
                    overdue_amount += outstanding
        
        return {
            "total_outstanding": str(total_outstanding),
            "overdue_amount": str(overdue_amount),
            "current_amount": str(total_outstanding - overdue_amount),
            "outstanding_count": len(outstanding_invoices)
        }
    
    @staticmethod
    def generate_payment_receipt(payment_id):
        """Generate payment receipt data"""
        payment = Payment.query.get(payment_id)
        if not payment:
            return None
        
        invoice = Invoice.query.get(payment.invoice_id)
        customer = Customer.query.get(payment.customer_id)
        
        return {
            "receipt_number": f"RCP-{payment.id}",
            "payment_date": payment.payment_date.isoformat(),
            "customer": {
                "name": customer.contact_person,
                "business_name": customer.business_name,
                "phone": customer.phone,
                "email": customer.email
            },
            "invoice": {
                "invoice_number": invoice.invoice_number,
                "invoice_date": invoice.invoice_date.isoformat(),
                "grand_total": str(invoice.grand_total)
            },
            "payment": {
                "amount_before_discount": str(payment.amount_before_discount),
                "discount_amount": str(payment.discount_amount),
                "amount_paid": str(payment.amount_paid),
                "payment_method": payment.payment_method,
                "transaction_reference": payment.transaction_reference,
                "bank_details": payment.bank_details
            }
        }
