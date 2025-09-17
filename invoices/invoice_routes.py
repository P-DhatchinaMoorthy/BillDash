from flask import Blueprint, request, jsonify, send_file, make_response
from invoices.invoice_service import InvoiceService
from invoices.invoice import Invoice
from src.extensions import db
from sqlalchemy import or_
from user.enhanced_auth_middleware import require_permission_jwt
from user.audit_logger import audit_decorator
import pandas as pd
import io
from datetime import datetime

bp = Blueprint("invoices", __name__)


@bp.route("/", methods=["POST"])
@require_permission_jwt('invoices', 'write')
@audit_decorator('invoices', 'CREATE')
def create_invoice():
    payload = request.get_json() or {}
    customer_id = payload.get("customer_id")
    items = payload.get("items")  # list of {product_id, quantity, discount_per_item(optional), discount_type(optional)}
    if not items or not isinstance(items, list):
        return jsonify({"error": "items list is required"}), 400
    try:
        from datetime import datetime
        due_date_str = payload.get("due_date")
        due_date = datetime.strptime(due_date_str, "%Y-%m-%d") if due_date_str else None

        invoice = InvoiceService.create_invoice(
            customer_id=customer_id,
            items=items,
            payment_terms=payload.get("payment_terms"),
            currency=payload.get("currency", "INR"),
            notes=payload.get("notes"),
            due_date=due_date,
            shipping_charges=payload.get("shipping_charges", 0),
            other_charges=payload.get("other_charges", 0),
            additional_discount=payload.get("additional_discount", 0),
            additional_discount_type=payload.get("additional_discount_type", "percentage")
        )

        from payments.payment import Payment
        from src.extensions import db as ext_db
        payment = Payment(
            invoice_id=invoice.id,
            customer_id=customer_id,
            amount_before_discount=invoice.grand_total,
            amount_paid=0,
            payment_method="Pending",
            payment_status="Pending"
        )
        ext_db.session.add(payment)
        ext_db.session.commit()

        # Get customer details for response
        from customers.customer import Customer
        customer = Customer.query.get(customer_id)

        return jsonify({
            "invoice_id": invoice.id,
            "payment_id": payment.id,
            "invoice_number": invoice.invoice_number,
            "customer_details": {
                "customer_id": customer.id,
                "customer_name": customer.contact_person,
                "business_name": customer.business_name
            },
            "invoice_totals": {
                "total_before_tax": str(invoice.total_before_tax),
                "tax_amount": str(invoice.tax_amount),
                "cgst_amount": str(invoice.cgst_amount),
                "sgst_amount": str(invoice.sgst_amount),
                "igst_amount": str(invoice.igst_amount),
                "discount_amount": str(invoice.discount_amount),
                "shipping_charges": str(invoice.shipping_charges),
                "other_charges": str(invoice.other_charges),
                "additional_discount": str(invoice.additional_discount),
                "grand_total": str(invoice.grand_total)
            },
            "invoice_details": {
                "currency": invoice.currency,
                "payment_terms": invoice.payment_terms,
                "status": invoice.status,
                "invoice_date": invoice.invoice_date.isoformat(),
                "total_items": len(items)
            }
        }), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/", methods=["GET"])
@require_permission_jwt('invoices', 'read')
def list_invoices():
    try:
        query = Invoice.query

        # Search filters
        customer_search = request.args.get('customer')
        status_filter = request.args.get('status')
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')

        # Filter by customer (name or business name)
        if customer_search:
            from customers.customer import Customer
            customer_ids = db.session.query(Customer.id).filter(
                or_(
                    Customer.contact_person.ilike(f'%{customer_search}%'),
                    Customer.business_name.ilike(f'%{customer_search}%')
                )
            ).subquery()
            query = query.filter(Invoice.customer_id.in_(customer_ids))

        # Filter by status
        if status_filter:
            query = query.filter(Invoice.status.ilike(f'%{status_filter}%'))

        # Filter by date range
        if date_from:
            from datetime import datetime
            date_from_obj = datetime.strptime(date_from, "%Y-%m-%d")
            query = query.filter(Invoice.invoice_date >= date_from_obj)

        if date_to:
            from datetime import datetime
            date_to_obj = datetime.strptime(date_to, "%Y-%m-%d")
            query = query.filter(Invoice.invoice_date <= date_to_obj)

        invoices = query.order_by(Invoice.created_at.desc()).all()
        result = []

        for i in invoices:
            from customers.customer import Customer
            from payments.payment import Payment
            from invoices.invoice_item import InvoiceItem
            from products.product import Product

            customer = Customer.query.get(i.customer_id)

            # Get payment ID for this invoice
            payments = Payment.query.filter_by(invoice_id=i.id).all()
            payment_id = payments[0].id if payments else None

            # Get invoice items with product details
            invoice_items = InvoiceItem.query.filter_by(invoice_id=i.id).all()
            items = []
            for item in invoice_items:
                product = Product.query.get(item.product_id)
                items.append({
                    "product_id": item.product_id,
                    "product_name": product.product_name if product else None,
                    "sku": product.sku if product else None,
                    "quantity": item.quantity,
                    "unit_price": str(item.unit_price),
                    "discount_per_item": str(item.discount_per_item),
                    "discount_type": item.discount_type,
                    "tax_rate_per_item": str(item.tax_rate_per_item),
                    "total_price": str(item.total_price)
                })

            result.append({
                "id": i.id,
                "invoice_number": i.invoice_number,
                "customer_id": i.customer_id,
                "customer_name": customer.contact_person if customer else None,
                "business_name": customer.business_name if customer else None,
                "branch": customer.branch if customer else None,
                "invoice_date": i.invoice_date.isoformat(),
                "due_date": i.due_date.isoformat() if i.due_date else None,
                "total_before_tax": str(i.total_before_tax),
                "tax_amount": str(i.tax_amount),
                "cgst_amount": str(getattr(i, 'cgst_amount', 0)),
                "sgst_amount": str(getattr(i, 'sgst_amount', 0)),
                "igst_amount": str(getattr(i, 'igst_amount', 0)),
                "discount_amount": str(i.discount_amount),
                "shipping_charges": str(i.shipping_charges),
                "other_charges": str(i.other_charges),
                "additional_discount": str(getattr(i, 'additional_discount', 0)),
                "grand_total": str(i.grand_total),
                "payment_terms": i.payment_terms,
                "currency": i.currency,
                "status": i.status,
                "notes": i.notes,
                "payment_id": payment_id,
                "items": items,
                "created_at": i.created_at.isoformat(),
                "updated_at": i.updated_at.isoformat() if i.updated_at else None
            })
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/customer/<int:customer_id>", methods=["GET"])
@require_permission_jwt('invoices', 'read')
def get_invoices_by_customer_id(customer_id):
    try:
        from customers.customer import Customer
        from payments.payment import Payment
        from invoices.invoice_item import InvoiceItem
        from products.product import Product

        customer = Customer.query.get(customer_id)
        if not customer:
            return jsonify({"error": "Customer not found"}), 404

        invoices = Invoice.query.filter_by(customer_id=customer_id).order_by(Invoice.created_at.desc()).all()

        result = []
        for invoice in invoices:
            payment = Payment.query.filter_by(invoice_id=invoice.id).first()
            payment_status = "pending"
            if payment:
                if payment.payment_status.lower() == "successful":
                    payment_status = "paid"
                elif payment.payment_status.lower() == "partially paid":
                    payment_status = "partially_paid"
                else:
                    payment_status = "pending"

            # Get invoice items with product details
            invoice_items = InvoiceItem.query.filter_by(invoice_id=invoice.id).all()
            items = []
            for item in invoice_items:
                product = Product.query.get(item.product_id)
                items.append({
                    "product_id": item.product_id,
                    "product_name": product.product_name if product else None,
                    "sku": product.sku if product else None,
                    "quantity": item.quantity,
                    "unit_price": str(item.unit_price),
                    "discount_per_item": str(item.discount_per_item),
                    "discount_type": item.discount_type,
                    "tax_rate_per_item": str(item.tax_rate_per_item),
                    "total_price": str(item.total_price)
                })

            result.append({
                "invoice_id": invoice.id,
                "invoice_number": invoice.invoice_number,
                "customer_id": invoice.customer_id,
                "amount": float(invoice.grand_total),
                "invoice_date": invoice.invoice_date.strftime("%Y-%m-%d"),
                "due_date": invoice.due_date.strftime("%Y-%m-%d") if invoice.due_date else None,
                "payment_status": payment_status,
                "items": items
            })

        return jsonify({
            "customer": {
                "id": customer.id,
                "business_name": customer.business_name,
                "contact_person": customer.contact_person
            },
            "invoices": result
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("customer/<int:customer_id>/", methods=["GET"])
@require_permission_jwt('invoices', 'read')
def get_invoices_by_customer(customer_id):
    try:
        from customers.customer import Customer
        from payments.payment import Payment
        from invoices.invoice_item import InvoiceItem
        from products.product import Product

        customer = Customer.query.get(customer_id)
        if not customer:
            return jsonify({"error": "Customer not found"}), 404

        # Get payment status filter
        payment_status_filter = request.args.get('payment_status')

        invoices = Invoice.query.filter_by(customer_id=customer_id).order_by(Invoice.created_at.desc()).all()

        if not invoices:
            return jsonify({
                "customer": {
                    "id": customer.id,
                    "business_name": customer.business_name,
                    "contact_person": customer.contact_person
                },
                "invoices": [],
                "message": "No invoices found for this customer"
            }), 200

        result = []
        for invoice in invoices:
            payment = Payment.query.filter_by(invoice_id=invoice.id).first()
            payment_status = "pending"
            if payment:
                if payment.payment_status.lower() == "successful":
                    payment_status = "paid"
                elif payment.payment_status.lower() == "partially paid":
                    payment_status = "partially_paid"
                else:
                    payment_status = "pending"

            # Apply payment status filter
            if payment_status_filter and payment_status != payment_status_filter.lower():
                continue

            # Get invoice items with product details
            invoice_items = InvoiceItem.query.filter_by(invoice_id=invoice.id).all()
            items = []
            for item in invoice_items:
                product = Product.query.get(item.product_id)
                items.append({
                    "product_id": item.product_id,
                    "product_name": product.product_name if product else None,
                    "sku": product.sku if product else None,
                    "quantity": item.quantity,
                    "unit_price": str(item.unit_price),
                    "discount_per_item": str(item.discount_per_item),
                    "discount_type": item.discount_type,
                    "tax_rate_per_item": str(item.tax_rate_per_item),
                    "total_price": str(item.total_price)
                })

            result.append({
                "invoice_id": invoice.id,
                "invoice_number": invoice.invoice_number,
                "customer_id": invoice.customer_id,
                "amount": float(invoice.grand_total),
                "invoice_date": invoice.invoice_date.strftime("%Y-%m-%d"),
                "due_date": invoice.due_date.strftime("%Y-%m-%d") if invoice.due_date else None,
                "payment_status": payment_status,
                "items": items
            })

        return jsonify({
            "customer": {
                "id": customer.id,
                "business_name": customer.business_name,
                "contact_person": customer.contact_person
            },
            "invoices": result
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/<int:invoice_id>", methods=["GET"])
@require_permission_jwt('invoices', 'read')
def get_invoice_by_id(invoice_id):
    try:
        invoice = Invoice.query.get(invoice_id)
        if not invoice:
            return jsonify({"error": "Invoice not found"}), 404

        from customers.customer import Customer
        from payments.payment import Payment
        from invoices.invoice_item import InvoiceItem
        from products.product import Product

        customer = Customer.query.get(invoice.customer_id)
        payments = Payment.query.filter_by(invoice_id=invoice.id).all()

        # Get invoice items with product details
        invoice_items = InvoiceItem.query.filter_by(invoice_id=invoice.id).all()
        items = []
        for item in invoice_items:
            product = Product.query.get(item.product_id)
            items.append({
                "product_id": item.product_id,
                "product_name": product.product_name if product else None,
                "sku": product.sku if product else None,
                "quantity": item.quantity,
                "unit_price": str(item.unit_price),
                "discount_per_item": str(item.discount_per_item),
                "discount_type": item.discount_type,
                "tax_rate_per_item": str(item.tax_rate_per_item),
                "total_price": str(item.total_price)
            })

        return jsonify({
            "invoice_id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "customer_id": invoice.customer_id,
            "customer_name": customer.contact_person if customer else None,
            "business_name": customer.business_name if customer else None,
            "invoice_date": invoice.invoice_date.isoformat(),
            "due_date": invoice.due_date.isoformat() if invoice.due_date else None,
            "cgst_amount": str(invoice.cgst_amount),
            "sgst_amount": str(invoice.sgst_amount),
            "igst_amount": str(invoice.igst_amount),
            "total_before_tax": str(invoice.total_before_tax),
            "tax_amount": str(invoice.tax_amount),
            "discount_amount": str(invoice.discount_amount),
            "shipping_charges": str(invoice.shipping_charges),
            "other_charges": str(invoice.other_charges),
            "additional_discount": str(getattr(invoice, 'additional_discount', 0)),
            "grand_total": str(invoice.grand_total),
            "payment_terms": invoice.payment_terms,
            "currency": invoice.currency,
            "status": invoice.status,
            "notes": invoice.notes,
            "items": items,
            "payments": [{
                "payment_id": p.id,
                "amount_paid": str(p.amount_paid),
                "payment_method": p.payment_method,
                "payment_status": p.payment_status
            } for p in payments]
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/search", methods=["GET"])
@require_permission_jwt('invoices', 'read')
def search_invoices():
    try:
        search_term = request.args.get('q', '')
        query = Invoice.query

        if search_term:
            from customers.customer import Customer

            customer_ids = db.session.query(Customer.id).filter(
                or_(
                    Customer.contact_person.ilike(f'%{search_term}%'),
                    Customer.business_name.ilike(f'%{search_term}%')
                )
            ).subquery()

            query = query.filter(
                or_(
                    Invoice.invoice_number.ilike(f'%{search_term}%'),
                    Invoice.customer_id.in_(customer_ids)
                )
            )

        invoices = query.order_by(Invoice.created_at.desc()).limit(50).all()
        result = []

        for i in invoices:
            from customers.customer import Customer
            from invoices.invoice_item import InvoiceItem
            from products.product import Product

            customer = Customer.query.get(i.customer_id)

            # Get invoice items with product details
            invoice_items = InvoiceItem.query.filter_by(invoice_id=i.id).all()
            items = []
            for item in invoice_items:
                product = Product.query.get(item.product_id)
                items.append({
                    "product_id": item.product_id,
                    "product_name": product.product_name if product else None,
                    "sku": product.sku if product else None,
                    "quantity": item.quantity,
                    "unit_price": str(item.unit_price),
                    "discount_per_item": str(item.discount_per_item),
                    "discount_type": item.discount_type,
                    "tax_rate_per_item": str(item.tax_rate_per_item),
                    "total_price": str(item.total_price)
                })

            result.append({
                "id": i.id,
                "invoice_number": i.invoice_number,
                "customer_name": customer.contact_person if customer else None,
                "business_name": customer.business_name if customer else None,
                "branch": customer.branch if customer else None,
                "grand_total": str(i.grand_total),
                "status": i.status,
                "invoice_date": i.invoice_date.isoformat(),
                "items": items
            })

        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/filter", methods=["GET"])
@require_permission_jwt('invoices', 'read')
def filter_invoices():
    try:
        status = request.args.get('status', 'all').lower()

        if status == 'all':
            invoices = Invoice.query.order_by(Invoice.created_at.desc()).all()
        else:
            invoices = Invoice.query.filter(Invoice.status.ilike(f'%{status}%')).order_by(
                Invoice.created_at.desc()).all()

        result = []
        for i in invoices:
            from customers.customer import Customer
            from invoices.invoice_item import InvoiceItem
            from products.product import Product

            customer = Customer.query.get(i.customer_id)

            # Get invoice items with product details
            invoice_items = InvoiceItem.query.filter_by(invoice_id=i.id).all()
            items = []
            for item in invoice_items:
                product = Product.query.get(item.product_id)
                items.append({
                    "product_id": item.product_id,
                    "product_name": product.product_name if product else None,
                    "sku": product.sku if product else None,
                    "quantity": item.quantity,
                    "unit_price": str(item.unit_price),
                    "discount_per_item": str(item.discount_per_item),
                    "discount_type": item.discount_type,
                    "tax_rate_per_item": str(item.tax_rate_per_item),
                    "total_price": str(item.total_price)
                })

            result.append({
                "id": i.id,
                "invoice_number": i.invoice_number,
                "customer_name": customer.contact_person if customer else None,
                "business_name": customer.business_name if customer else None,
                "branch": customer.branch if customer else None,
                "grand_total": str(i.grand_total),
                "status": i.status,
                "invoice_date": i.invoice_date.isoformat(),
                "items": items
            })

        return jsonify({
            "status_filter": status,
            "count": len(result),
            "invoices": result
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/<int:customer_id>", methods=["GET"])
@require_permission_jwt('invoices', 'read')
def get_invoices_for_customer(customer_id):
    try:
        from customers.customer import Customer
        from payments.payment import Payment
        from invoices.invoice_item import InvoiceItem
        from products.product import Product

        customer = Customer.query.get(customer_id)
        if not customer:
            return jsonify({"error": "Customer not found"}), 404

        invoices = Invoice.query.filter_by(customer_id=customer_id).order_by(Invoice.created_at.desc()).all()

        result = []
        for invoice in invoices:
            payment = Payment.query.filter_by(invoice_id=invoice.id).first()
            payment_status = "pending"
            if payment:
                if payment.payment_status.lower() == "successful":
                    payment_status = "paid"
                elif payment.payment_status.lower() == "partially paid":
                    payment_status = "partially_paid"
                else:
                    payment_status = "pending"

            # Get invoice items with product details
            invoice_items = InvoiceItem.query.filter_by(invoice_id=invoice.id).all()
            items = []
            for item in invoice_items:
                product = Product.query.get(item.product_id)
                items.append({
                    "product_id": item.product_id,
                    "product_name": product.product_name if product else None,
                    "sku": product.sku if product else None,
                    "quantity": item.quantity,
                    "unit_price": str(item.unit_price),
                    "discount_per_item": str(item.discount_per_item),
                    "discount_type": item.discount_type,
                    "tax_rate_per_item": str(item.tax_rate_per_item),
                    "total_price": str(item.total_price)
                })

            result.append({
                "invoice_id": invoice.id,
                "invoice_number": invoice.invoice_number,
                "customer_id": invoice.customer_id,
                "amount": float(invoice.grand_total),
                "invoice_date": invoice.invoice_date.strftime("%Y-%m-%d"),
                "due_date": invoice.due_date.strftime("%Y-%m-%d") if invoice.due_date else None,
                "payment_status": payment_status,
                "items": items
            })

        return jsonify({
            "customer": {
                "id": customer.id,
                "business_name": customer.business_name,
                "contact_person": customer.contact_person
            },
            "invoices": result
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/<int:invoice_id>", methods=["PUT"])
@require_permission_jwt('invoices', 'write')
@audit_decorator('invoices', 'UPDATE')
def update_invoice(invoice_id):
    from datetime import datetime
    from decimal import Decimal
    from invoices.invoice_item import InvoiceItem
    from products.product import Product
    from category.category import Category
    from stock_transactions.stock_transaction import StockTransaction
    from payments.payment import Payment
    
    invoice = Invoice.query.get(invoice_id)
    if not invoice:
        return jsonify({"error": "Invoice not found"}), 404

    data = request.get_json() or {}
    try:
        # Get current invoice items for stock reversal
        current_items = InvoiceItem.query.filter_by(invoice_id=invoice_id).all()
        
        # Reverse stock for current items
        for item in current_items:
            product = Product.query.get(item.product_id)
            if product:
                product.quantity_in_stock += item.quantity
                # Create reverse stock transaction
                stock_txn = StockTransaction(
                    product_id=product.id,
                    transaction_type="Return",
                    sale_type="Invoice Update",
                    quantity=item.quantity,
                    invoice_id=invoice.id
                )
                db.session.add(stock_txn)
        
        # Delete current invoice items
        InvoiceItem.query.filter_by(invoice_id=invoice_id).delete()
        
        # Process new items if provided
        new_items = data.get("items", [])
        if new_items:
            total_before_tax = Decimal("0.00")
            total_tax = Decimal("0.00")
            total_cgst = Decimal("0.00")
            total_sgst = Decimal("0.00")
            total_igst = Decimal("0.00")
            total_discount = Decimal("0.00")
            
            for item_data in new_items:
                product = Product.query.get(item_data["product_id"])
                if not product:
                    raise ValueError(f"Product {item_data['product_id']} not found")
                
                qty = int(item_data.get("quantity", 1))
                if product.quantity_in_stock < qty:
                    raise ValueError(f"Insufficient stock for {product.product_name}")
                
                unit_price = Decimal(product.selling_price)
                discount_per_item = Decimal(item_data.get("discount_per_item", 0))
                discount_type = item_data.get("discount_type", "percentage")
                
                # Get tax rates
                category = Category.query.get(product.category_id) if product.category_id else None
                if category:
                    cgst_rate = Decimal(category.cgst_rate)
                    sgst_rate = Decimal(category.sgst_rate)
                    igst_rate = Decimal(category.igst_rate)
                else:
                    cgst_rate = sgst_rate = igst_rate = Decimal("0")
                
                # Calculate amounts
                line_subtotal = unit_price * qty
                if discount_type == "percentage":
                    discount_amount = (line_subtotal * discount_per_item / Decimal("100.00")).quantize(Decimal("0.01"))
                else:
                    discount_amount = Decimal(str(discount_per_item)).quantize(Decimal("0.01"))
                
                if discount_amount > line_subtotal:
                    discount_amount = line_subtotal
                
                line_after_discount = (line_subtotal - discount_amount).quantize(Decimal("0.01"))
                cgst_amount = (line_after_discount * cgst_rate / Decimal("100.00")).quantize(Decimal("0.01"))
                sgst_amount = (line_after_discount * sgst_rate / Decimal("100.00")).quantize(Decimal("0.01"))
                igst_amount = (line_after_discount * igst_rate / Decimal("100.00")).quantize(Decimal("0.01"))
                tax_amount = igst_amount
                line_total = (line_after_discount + tax_amount).quantize(Decimal("0.01"))
                
                # Create new invoice item
                invoice_item = InvoiceItem(
                    invoice_id=invoice.id,
                    product_id=product.id,
                    quantity=qty,
                    unit_price=unit_price,
                    discount_per_item=discount_per_item,
                    discount_type=discount_type,
                    tax_rate_per_item=igst_rate,
                    cgst_rate=cgst_rate,
                    sgst_rate=sgst_rate,
                    igst_rate=igst_rate,
                    cgst_amount=cgst_amount,
                    sgst_amount=sgst_amount,
                    igst_amount=igst_amount,
                    total_price=line_total
                )
                db.session.add(invoice_item)
                
                # Update stock and create transaction
                product.quantity_in_stock -= qty
                stock_txn = StockTransaction(
                    product_id=product.id,
                    transaction_type="Sale",
                    sale_type="With Bill",
                    quantity=qty,
                    invoice_id=invoice.id
                )
                db.session.add(stock_txn)
                
                # Update totals
                total_before_tax += line_after_discount
                total_tax += tax_amount
                total_cgst += cgst_amount
                total_sgst += sgst_amount
                total_igst += igst_amount
                total_discount += discount_amount
            
            # Update invoice totals
            invoice.total_before_tax = total_before_tax.quantize(Decimal("0.00"))
            invoice.tax_amount = total_tax.quantize(Decimal("0.00"))
            invoice.cgst_amount = total_cgst.quantize(Decimal("0.00"))
            invoice.sgst_amount = total_sgst.quantize(Decimal("0.00"))
            invoice.igst_amount = total_igst.quantize(Decimal("0.00"))
            invoice.discount_amount = total_discount.quantize(Decimal("0.00"))
        
        # Update other invoice fields
        invoice.payment_terms = data.get("payment_terms", invoice.payment_terms)
        invoice.notes = data.get("notes", invoice.notes)
        invoice.shipping_charges = Decimal(str(data.get("shipping_charges", invoice.shipping_charges)))
        invoice.other_charges = Decimal(str(data.get("other_charges", invoice.other_charges)))
        
        # Handle additional discount
        additional_discount = Decimal(str(data.get("additional_discount", invoice.additional_discount or 0)))
        additional_discount_type = data.get("additional_discount_type", "percentage")
        
        if additional_discount > 0:
            subtotal_with_tax = invoice.total_before_tax + invoice.tax_amount
            if additional_discount_type == "percentage":
                additional_discount_amount = (subtotal_with_tax * additional_discount / Decimal("100.00")).quantize(Decimal("0.01"))
            else:
                additional_discount_amount = additional_discount.quantize(Decimal("0.01"))
        else:
            additional_discount_amount = Decimal("0.00")
        
        invoice.additional_discount = additional_discount_amount
        
        # Calculate final grand total
        subtotal_with_tax = invoice.total_before_tax + invoice.tax_amount
        invoice.grand_total = (subtotal_with_tax - additional_discount_amount + invoice.shipping_charges + invoice.other_charges).quantize(Decimal("0.00"))
        
        # Update due date
        if "due_date" in data and data["due_date"]:
            invoice.due_date = datetime.strptime(data["due_date"], "%Y-%m-%d")
        
        # Update payment amount
        payment = Payment.query.filter_by(invoice_id=invoice.id).first()
        if payment:
            payment.amount_before_discount = invoice.grand_total
        
        invoice.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            "invoice_id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "grand_total": str(invoice.grand_total),
            "total_before_tax": str(invoice.total_before_tax),
            "tax_amount": str(invoice.tax_amount),
            "discount_amount": str(invoice.discount_amount),
            "shipping_charges": str(invoice.shipping_charges),
            "other_charges": str(invoice.other_charges),
            "additional_discount": str(invoice.additional_discount),
            "status": invoice.status,
            "message": "Invoice updated successfully with stock adjustments"
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400


@bp.route("/bulk-import", methods=["POST"])
@require_permission_jwt('invoices', 'write')
@audit_decorator('invoices', 'BULK_IMPORT')
def bulk_import_invoices():
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No file uploaded"}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "No file selected"}), 400

        # Read file
        if file.filename.endswith('.csv'):
            df = pd.read_csv(io.StringIO(file.read().decode('utf-8')))
        elif file.filename.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(io.BytesIO(file.read()))
        else:
            return jsonify({"error": "Only CSV and Excel files supported"}), 400

        # Validate columns
        required_cols = ['customer_id', 'product_id', 'quantity']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            return jsonify({"error": f"Missing columns: {missing_cols}"}), 400

        results = []
        success_count = 0

        # Process each row
        for index, row in df.iterrows():
            try:
                # Start new session for each row to avoid rollback issues
                from src.extensions import db as main_db

                items = [{
                    "product_id": int(row['product_id']),
                    "quantity": int(row['quantity']),
                    "tax_rate_per_item": float(row.get('tax_rate', 0))
                }]

                invoice = InvoiceService.create_invoice(
                    customer_id=int(row['customer_id']),
                    items=items,
                    payment_terms=row.get('payment_terms'),
                    notes=row.get('notes')
                )

                # Create payment record
                from payments.payment import Payment
                payment = Payment(
                    invoice_id=invoice.id,
                    customer_id=int(row['customer_id']),
                    amount_before_discount=invoice.grand_total,
                    amount_paid=0,
                    payment_method="Pending",
                    payment_status="Pending"
                )
                main_db.session.add(payment)
                main_db.session.commit()

                results.append({
                    "row": index + 1,
                    "status": "success",
                    "invoice_id": invoice.id,
                    "invoice_number": invoice.invoice_number
                })
                success_count += 1

            except Exception as e:
                main_db.session.rollback()
                results.append({
                    "row": index + 1,
                    "status": "error",
                    "error": str(e)
                })

        return jsonify({
            "success_count": success_count,
            "total_rows": len(df),
            "results": results
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/export", methods=["GET"])
@require_permission_jwt('invoices', 'read')
def export_invoices():
    try:
        from flask import send_file, make_response
        import pandas as pd
        import io

        format_type = request.args.get('format', 'csv').lower()

        # Get all invoices with customer and payment data
        invoices = Invoice.query.order_by(Invoice.created_at.desc()).all()

        # Separate invoices by status
        paid_invoices = []
        pending_invoices = []
        partially_paid_invoices = []

        for invoice in invoices:
            from customers.customer import Customer
            from payments.payment import Payment

            customer = Customer.query.get(invoice.customer_id)
            payments = Payment.query.filter_by(invoice_id=invoice.id).all()
            total_paid = sum(float(p.amount_paid) for p in payments)

            # Determine actual status based on payments
            if total_paid >= float(invoice.grand_total):
                status = "Paid"
            elif total_paid > 0:
                status = "Partially Paid"
            else:
                status = "Pending"

            invoice_data = {
                'invoice_id': invoice.id,
                'invoice_number': invoice.invoice_number,
                'customer_name': customer.contact_person if customer else '',
                'business_name': customer.business_name if customer else '',
                'invoice_date': invoice.invoice_date.strftime('%Y-%m-%d'),
                'due_date': invoice.due_date.strftime('%Y-%m-%d') if invoice.due_date else '',
                'total_before_tax': float(invoice.total_before_tax),
                'tax_amount': float(invoice.tax_amount),
                'discount_amount': float(invoice.discount_amount),
                'shipping_charges': float(invoice.shipping_charges),
                'other_charges': float(invoice.other_charges),
                'grand_total': float(invoice.grand_total),
                'amount_paid': total_paid,
                'balance_due': float(invoice.grand_total) - total_paid,
                'payment_terms': invoice.payment_terms or '',
                'currency': invoice.currency,
                'status': status,
                'notes': invoice.notes or ''
            }

            if status == "Paid":
                paid_invoices.append(invoice_data)
            elif status == "Partially Paid":
                partially_paid_invoices.append(invoice_data)
            else:
                pending_invoices.append(invoice_data)

        if format_type == 'excel':
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                if paid_invoices:
                    pd.DataFrame(paid_invoices).to_excel(writer, sheet_name='Paid', index=False)
                if pending_invoices:
                    pd.DataFrame(pending_invoices).to_excel(writer, sheet_name='Pending', index=False)
                if partially_paid_invoices:
                    pd.DataFrame(partially_paid_invoices).to_excel(writer, sheet_name='Partially Paid', index=False)

            output.seek(0)
            return send_file(
                output,
                as_attachment=True,
                download_name='invoices_export.xlsx',
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
        else:
            # For CSV, combine all with status column
            all_invoices = paid_invoices + pending_invoices + partially_paid_invoices
            df = pd.DataFrame(all_invoices)

            output = io.StringIO()
            df.to_csv(output, index=False)
            response = make_response(output.getvalue())
            response.headers['Content-Type'] = 'text/csv; charset=utf-8'
            response.headers['Content-Disposition'] = 'attachment; filename=invoices_export.csv'
            return response

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route("/<int:invoice_id>", methods=["DELETE"])
@require_permission_jwt('invoices', 'write')
@audit_decorator('invoices', 'DELETE')
def delete_invoice(invoice_id):
    invoice = Invoice.query.get(invoice_id)
    if not invoice:
        return jsonify({"error": "Invoice not found"}), 404
    
    try:
        # Delete related invoice items and payments first
        from invoices.invoice_item import InvoiceItem
        from payments.payment import Payment
        
        InvoiceItem.query.filter_by(invoice_id=invoice_id).delete()
        Payment.query.filter_by(invoice_id=invoice_id).delete()
        
        db.session.delete(invoice)
        db.session.commit()
        return jsonify({"message": "Invoice deleted successfully"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400