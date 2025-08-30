# services/sales_service.py
from decimal import Decimal
from src.extensions import db
from customers.customer import Customer
from products.product import Product
from invoices.invoice import Invoice
from invoices.invoice_item import InvoiceItem
from payments.payment import Payment
from stock_transactions.stock_transaction import StockTransaction
from datetime import datetime
import uuid

class SalesService:
    @staticmethod
    def create_sale_with_payment(customer_id, items, payment_method, payment_amount, discount_percentage=0, bank_details=None, transaction_reference=None):
        """
        Complete sales workflow: Create invoice, process payment, update stock.
        items = [{"product_id": "uuid", "quantity": 2}, ...]
        """
        customer = Customer.query.get(customer_id)
        if not customer:
            raise ValueError("Customer not found")
        
        # Validate products and stock
        invoice_items = []
        total_before_tax = Decimal('0')
        
        for item in items:
            product = Product.query.get(item["product_id"])
            if not product:
                raise ValueError(f"Product {item['product_id']} not found")
            
            if product.quantity_in_stock < item["quantity"]:
                raise ValueError(f"Insufficient stock for {product.product_name}. Available: {product.quantity_in_stock}")
            
            item_total = Decimal(product.selling_price) * item["quantity"]
            total_before_tax += item_total
            
            invoice_items.append({
                "product": product,
                "quantity": item["quantity"],
                "unit_price": product.selling_price,
                "total_price": item_total
            })
        
        # Calculate tax (18% GST)
        tax_rate = Decimal('18')
        tax_amount = (total_before_tax * tax_rate / Decimal('100')).quantize(Decimal('0.01'))
        grand_total = total_before_tax + tax_amount
        
        # Create invoice
        invoice = Invoice(
            invoice_number=f"INV-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            customer_id=customer_id,
            total_before_tax=total_before_tax,
            tax_amount=tax_amount,
            grand_total=grand_total,
            status="Pending"
        )
        db.session.add(invoice)
        db.session.flush()  # Get invoice ID
        
        # Create invoice items
        for item_data in invoice_items:
            invoice_item = InvoiceItem(
                invoice_id=invoice.id,
                product_id=item_data["product"].id,
                quantity=item_data["quantity"],
                unit_price=item_data["unit_price"],
                tax_rate_per_item=tax_rate,
                total_price=item_data["total_price"]
            )
            db.session.add(invoice_item)
        
        # Process payment
        payment_amount_decimal = Decimal(payment_amount)
        discount_pct = Decimal(discount_percentage or 0)
        discount_amount = (payment_amount_decimal * discount_pct / Decimal('100')).quantize(Decimal('0.01'))
        amount_after_discount = payment_amount_decimal - discount_amount
        
        # Calculate balance and excess
        if amount_after_discount >= grand_total:
            balance_amount = Decimal('0')
            excess_amount = amount_after_discount - grand_total
            invoice.status = "Paid"
        else:
            balance_amount = grand_total - amount_after_discount
            excess_amount = Decimal('0')
            invoice.status = "Partially Paid"
        
        # Create payment
        payment = Payment(
            invoice_id=invoice.id,
            customer_id=customer_id,
            payment_method=payment_method,
            amount_before_discount=payment_amount_decimal,
            discount_percentage=discount_pct,
            discount_amount=discount_amount,
            amount_paid=amount_after_discount,
            balance_amount=balance_amount,
            excess_amount=excess_amount,
            bank_details=bank_details,
            transaction_reference=transaction_reference,
            payment_status="Successful"
        )
        db.session.add(payment)
        
        # Update stock quantities and create stock transactions
        for item in items:
            product = Product.query.get(item["product_id"])
            product.quantity_in_stock -= item["quantity"]
            
            # Create stock transaction
            stock_transaction = StockTransaction(
                product_id=item["product_id"],
                transaction_type="Sale",
                sale_type="With Bill",
                quantity=-item["quantity"],  # Negative for sale
                invoice_id=invoice.id,
                reference_number=invoice.invoice_number
            )
            db.session.add(stock_transaction)
        
        db.session.commit()
        
        return {
            "invoice_id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "payment_id": payment.id,
            "total_amount": str(grand_total),
            "amount_paid": str(amount_after_discount),
            "balance_amount": str(balance_amount),
            "excess_amount": str(excess_amount),
            "status": invoice.status
        }