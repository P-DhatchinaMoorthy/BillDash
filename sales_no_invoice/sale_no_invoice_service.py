# services/sale_no_invoice_service.py
from decimal import Decimal
from src.extensions import db
from sales_no_invoice.sale_no_invoice import SaleNoInvoice
from products.product import Product
from customers.customer import Customer
from stock_transactions.stock_transaction import StockTransaction

class SaleNoInvoiceService:
    @staticmethod
    def create_sale(product_id, quantity, discount_percentage, payment_method, customer_id=None, notes=None):
        """
        Create a sale without invoice:
         - fetch product and its selling_price
         - reduce stock
         - create SaleNoInvoice record
         - create StockTransaction (sale_type Without Bill)
        """
        product = Product.query.get(product_id)
        if not product:
            raise ValueError("Product not found")

        qty = int(quantity)
        if product.quantity_in_stock < qty:
            raise ValueError("Insufficient stock")

        unit_price = Decimal(product.selling_price)
        total_amount = (unit_price * qty).quantize(Decimal("0.01"))
        discount_pct = Decimal(discount_percentage or 0)
        discount_amt = (total_amount * discount_pct / Decimal('100')).quantize(Decimal('0.01'))
        amount_after_discount = total_amount - discount_amt

        # Deduct stock
        product.quantity_in_stock -= qty

        sale = SaleNoInvoice(
            product_id=product.id,
            quantity=qty,
            selling_price=unit_price,
            total_amount=total_amount,
            discount_percentage=discount_pct,
            discount_amount=discount_amt,
            amount_after_discount=amount_after_discount,
            payment_method=payment_method,
            customer_id=customer_id,
            notes=notes,
        )
        db.session.add(sale)

        stock_txn = StockTransaction(
            product_id=product.id,
            transaction_type="Sale",
            sale_type="Without Bill",
            quantity=-qty,
        )
        db.session.add(stock_txn)

        db.session.commit()
        return sale
