from decimal import Decimal
from src.extensions import db
from invoices.invoice import Invoice
from invoices.invoice_item import InvoiceItem
from products.product import Product
from category.category import Category
from stock_transactions.stock_transaction import StockTransaction
from datetime import datetime

class InvoiceService:
    @staticmethod
    def _generate_invoice_number(invoice_id):
        # Format: INV-YYYY-MM-ID
        now = datetime.utcnow()
        return f"INV-{now.strftime('%Y')}-{now.strftime('%m')}-{invoice_id}"

    @staticmethod
    def create_invoice(customer_id, items, payment_terms=None, currency="INR", notes=None, shipping_charges=0, other_charges=0, additional_discount=0, additional_discount_type="percentage", due_date=None):
        """
        items: list of dicts [{product_id, quantity, discount_per_item(optional), discount_type(optional)}]
        This function:
         - creates invoice header
         - creates invoice items (fetches selling_price from Product)
         - automatically fetches tax rates from product category
         - calculates totals
         - deducts stock and creates stock transactions
        """
        # Get next invoice ID to generate invoice number
        last_invoice = Invoice.query.order_by(Invoice.id.desc()).first()
        next_id = (last_invoice.id + 1) if last_invoice else 4001
        
        invoice = Invoice(
            customer_id=customer_id,
            invoice_number=InvoiceService._generate_invoice_number(next_id),
            payment_terms=payment_terms,
            currency=currency,
            notes=notes,
            due_date=due_date,
            shipping_charges=Decimal(str(shipping_charges)),
            other_charges=Decimal(str(other_charges)),
        )
        db.session.add(invoice)
        db.session.flush()

        total_before_tax = Decimal("0.00")
        total_tax = Decimal("0.00")
        total_cgst = Decimal("0.00")
        total_sgst = Decimal("0.00")
        total_igst = Decimal("0.00")
        total_discount = Decimal("0.00")

        for it in items:
            # Validate item structure
            if not isinstance(it, dict) or "product_id" not in it:
                db.session.rollback()
                raise ValueError(f"Invalid item format: {it}")
                
            product = Product.query.get(it["product_id"])
            if not product:
                db.session.rollback()
                raise ValueError(f"Product id {it['product_id']} not found")

            qty = int(it.get("quantity", 1))
            unit_price = Decimal(product.selling_price)
            discount_per_item = Decimal(it.get("discount_per_item", 0))
            discount_type = it.get("discount_type", "percentage")
            
            # Get tax rates from product category
            category = Category.query.get(product.category_id) if product.category_id else None
            if category:
                cgst_rate = Decimal(category.cgst_rate)
                sgst_rate = Decimal(category.sgst_rate)
                igst_rate = Decimal(category.igst_rate)
            else:
                cgst_rate = sgst_rate = igst_rate = Decimal("0")
            
            tax_rate = igst_rate  # Use IGST for calculation

            # Calculate line subtotal
            line_subtotal = unit_price * qty
            
            # Apply discount
            if discount_type == "percentage":
                discount_amount = (line_subtotal * discount_per_item / Decimal("100.00")).quantize(Decimal("0.01"))
            else:  # amount
                discount_amount = Decimal(str(discount_per_item)).quantize(Decimal("0.01"))
            
            # Ensure discount doesn't exceed line subtotal

            if discount_amount > line_subtotal:
                discount_amount = line_subtotal
                
            line_after_discount = (line_subtotal - discount_amount).quantize(Decimal("0.01"))
            
            # Calculate tax breakdown on discounted amount
            cgst_amount = (line_after_discount * cgst_rate / Decimal("100.00")).quantize(Decimal("0.01"))
            sgst_amount = (line_after_discount * sgst_rate / Decimal("100.00")).quantize(Decimal("0.01"))
            igst_amount = (line_after_discount * igst_rate / Decimal("100.00")).quantize(Decimal("0.01"))
            tax_amount = igst_amount  # Only IGST is charged
            line_total = (line_after_discount + tax_amount).quantize(Decimal("0.01"))

            invoice_item = InvoiceItem(
                invoice_id=invoice.id,
                product_id=product.id,
                quantity=qty,
                unit_price=unit_price,
                discount_per_item=discount_per_item,
                discount_type=discount_type,
                tax_rate_per_item=tax_rate,
                cgst_rate=cgst_rate,
                sgst_rate=sgst_rate,
                igst_rate=igst_rate,
                cgst_amount=cgst_amount,
                sgst_amount=sgst_amount,
                igst_amount=igst_amount,
                total_price=line_total,
            )
            db.session.add(invoice_item)

            # Update totals
            total_before_tax += line_after_discount
            total_tax += tax_amount
            total_cgst += cgst_amount
            total_sgst += sgst_amount
            total_igst += igst_amount
            total_discount += discount_amount

            # Deduct stock and create stock transaction
            if product.quantity_in_stock < qty:
                db.session.rollback()
                raise ValueError(f"Insufficient stock for product {product.product_name}")

            product.quantity_in_stock -= qty
            stock_txn = StockTransaction(
                product_id=product.id,
                transaction_type="Sale",
                sale_type="With Bill",
                quantity=qty,
                invoice_id=invoice.id,
            )
            db.session.add(stock_txn)

        # Calculate subtotal with tax
        subtotal_with_tax = (total_before_tax + total_tax).quantize(Decimal("0.00"))
        
        # Apply additional discount
        additional_discount_val = Decimal(str(additional_discount))
        if additional_discount_val > 0:
            if additional_discount_type == "percentage":
                additional_discount_amount = (subtotal_with_tax * additional_discount_val / Decimal("100.00")).quantize(Decimal("0.01"))
            else:  # amount
                additional_discount_amount = additional_discount_val.quantize(Decimal("0.01"))
        else:
            additional_discount_amount = Decimal("0.00")
        
        # Calculate final grand total
        grand_total_final = (subtotal_with_tax - additional_discount_amount + invoice.shipping_charges + invoice.other_charges).quantize(Decimal("0.00"))
        
        # finalize invoice totals
        invoice.total_before_tax = total_before_tax.quantize(Decimal("0.00"))
        invoice.tax_amount = total_tax.quantize(Decimal("0.00"))
        invoice.cgst_amount = total_cgst.quantize(Decimal("0.00"))
        invoice.sgst_amount = total_sgst.quantize(Decimal("0.00"))
        invoice.igst_amount = total_igst.quantize(Decimal("0.00"))
        invoice.discount_amount = total_discount.quantize(Decimal("0.00"))
        invoice.additional_discount = additional_discount_amount
        invoice.grand_total = grand_total_final

        db.session.commit()
        return invoice
