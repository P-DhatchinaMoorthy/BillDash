from flask import Blueprint, request, jsonify
from decimal import Decimal
from extensions import db
from payments.payment_service import PaymentService

bp = Blueprint("payments", __name__)

@bp.route("/direct-sale", methods=["POST"])
def direct_sale():
    from sales.direct_sales_service import DirectSalesService
    payload = request.get_json() or {}
    customer_id = payload.get("customer_id")
    customer_name = payload.get("customer_name")
    phone = payload.get("phone")
    payment_method = payload.get("payment_method")
    product_id = payload.get("product_id")
    quantity = payload.get("quantity")
    
    if not all([customer_id, customer_name, phone, payment_method, product_id, quantity]):
        return jsonify({"error": "customer_id, customer_name, phone, payment_method, product_id, quantity required"}), 400
    
    try:
        result = DirectSalesService.create_sale_and_invoice(
            customer_id=customer_id,
            customer_name=customer_name,
            phone=phone,
            payment_method=payment_method,
            product_id=product_id,
            quantity=quantity,
            discount_percentage=payload.get("discount_percentage", 0),
            bank_details=payload.get("bank_details"),
            transaction_reference=payload.get("transaction_reference")
        )
        return jsonify(result), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@bp.route("/", methods=["POST"])
def create_payment():
    payload = request.get_json() or {}
    invoice_id = payload.get("invoice_id")
    amount_paid = payload.get("amount_paid")
    payment_method = payload.get("payment_method")
    
    if not all([invoice_id, amount_paid, payment_method]):
        return jsonify({"error": "invoice_id, amount_paid, payment_method required"}), 400
    
    try:
        result = PaymentService.create_payment(
            invoice_id=invoice_id,
            amount=amount_paid,
            method=payment_method,
            discount_percentage=payload.get("discount_percentage", 0),
            bank_details=payload.get("bank_details"),
            transaction_reference=payload.get("transaction_reference"),
            notes=payload.get("notes")
        )
        return jsonify(result), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@bp.route("/", methods=["GET"])
def list_payments():
    from payments.payment import Payment
    from decimal import Decimal
    payments = Payment.query.all()
    result = []
    for p in payments:
        # Calculate correct status
        balance = Decimal(p.balance_amount or 0)
        amount_paid = Decimal(p.amount_paid or 0)
        
        if balance <= 0 and amount_paid > 0:
            status = "Successful"
        elif amount_paid > 0:
            status = "Partially Paid"
        else:
            status = "Pending"
            
        result.append({
            "id": p.id, 
            "invoice_id": p.invoice_id, 
            "customer_id": p.customer_id,
            "payment_date": p.payment_date.isoformat(),
            "payment_method": p.payment_method,
            "amount_before_discount": str(p.amount_before_discount),
            "discount_amount": str(p.discount_amount),
            "amount_paid": str(p.amount_paid),
            "balance_amount": str(p.balance_amount),
            "excess_amount": str(p.excess_amount),
            "payment_status": status
        })
    return jsonify(result), 200

@bp.route("/<payment_id>", methods=["GET"])
def get_payment(payment_id):
    from payments.payment import Payment
    from customers.customer import Customer
    from invoices.invoice import Invoice
    from decimal import Decimal
    
    p = Payment.query.get(payment_id)
    if not p:
        return jsonify({"error": "empty"}), 404
    
    # Get related data
    customer = Customer.query.get(p.customer_id) if p.customer_id else None
    invoice = Invoice.query.get(p.invoice_id) if p.invoice_id else None
        
    # Calculate correct status
    balance = Decimal(p.balance_amount or 0)
    amount_paid = Decimal(p.amount_paid or 0)
    
    if balance <= 0 and amount_paid > 0:
        status = "Successful"
    elif amount_paid > 0:
        status = "Partially Paid"
    else:
        status = "Pending"
        
    return jsonify({
        "payment_id": p.id, 
        "invoice_id": p.invoice_id,
        "invoice_number": invoice.invoice_number if invoice else None,
        "customer_details": {
            "customer_id": customer.id,
            "customer_name": customer.contact_person,
            "business_name": customer.business_name,
            "phone": customer.phone,
            "email": customer.email
        } if customer else None,
        "payment_details": {
            "payment_date": p.payment_date.isoformat(),
            "payment_method": p.payment_method,
            "amount_before_discount": str(p.amount_before_discount),
            "discount_percentage": str(p.discount_percentage),
            "discount_amount": str(p.discount_amount),
            "amount_paid": str(p.amount_paid),
            "balance_amount": str(p.balance_amount),
            "excess_amount": str(p.excess_amount),
            "payment_status": status,
            "transaction_reference": p.transaction_reference,
            "bank_details": p.bank_details
        }
    }), 200

@bp.route("/<payment_id>", methods=["PUT"])
def update_payment(payment_id):
    from payments.payment import Payment
    payment = Payment.query.get(payment_id)
    if not payment:
        return jsonify({"error": "Payment not found"}), 404
    
    data = request.get_json() or {}
    try:
        # Add to existing amount_paid if new amount provided
        if "amount_paid" in data:
            current_paid = Decimal(payment.amount_paid or 0)
            additional_amount = Decimal(str(data["amount_paid"]))
            payment.amount_paid = current_paid + additional_amount
        
        payment.payment_method = data.get("payment_method", payment.payment_method)
        payment.discount_percentage = data.get("discount_percentage", payment.discount_percentage)
        payment.bank_details = data.get("bank_details", payment.bank_details)
        payment.transaction_reference = data.get("transaction_reference", payment.transaction_reference)
        payment.notes = data.get("notes", payment.notes)
        
        # Auto-calculate amounts and status
        payment.calculate_amounts()
        db.session.commit()
        
        return jsonify({
            "payment_id": payment.id,
            "invoice_id": payment.invoice_id,
            "amount_paid": str(payment.amount_paid),
            "payment_method": payment.payment_method,
            "payment_status": payment.payment_status,
            "balance_amount": str(payment.balance_amount),
            "excess_amount": str(payment.excess_amount),
            "transaction_reference": payment.transaction_reference
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@bp.route("/<int:invoice_id>", methods=["POST"])
def process_payment_by_invoice(invoice_id):
    from payments.payment import Payment
    from invoices.invoice import Invoice
    
    # Get existing payment record or create new one
    payment = Payment.query.filter_by(invoice_id=invoice_id).first()
    if not payment:
        return jsonify({"error": "Payment not found for this invoice"}), 404
    
    data = request.get_json() or {}
    amount_paid = data.get("amount_paid")
    payment_method = data.get("payment_method")
    
    if not all([amount_paid, payment_method]):
        return jsonify({"error": "amount_paid and payment_method required"}), 400
    
    try:
        # Add to existing amount_paid (cumulative)
        current_paid = Decimal(payment.amount_paid or 0)
        new_amount = Decimal(str(amount_paid))
        payment.amount_paid = current_paid + new_amount
        
        payment.payment_method = payment_method
        payment.discount_percentage = data.get("discount_percentage", payment.discount_percentage)
        payment.bank_details = data.get("bank_details")
        payment.transaction_reference = data.get("transaction_reference")
        payment.notes = data.get("notes")
        
        # Auto-calculate amounts and status
        payment.calculate_amounts()
        db.session.commit()
        
        return jsonify({
            "payment_id": payment.id,
            "invoice_id": payment.invoice_id,
            "amount_paid": str(payment.amount_paid),
            "payment_method": payment.payment_method,
            "payment_status": payment.payment_status,
            "balance_amount": str(payment.balance_amount),
            "excess_amount": str(payment.excess_amount)
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@bp.route("/invoice/<invoice_id>/details", methods=["GET"])
def get_detailed_invoice(invoice_id):
    try:
        invoice_details = PaymentService.get_detailed_invoice(invoice_id)
        if not invoice_details:
            return jsonify({"error": "Invoice not found"}), 404
        return jsonify(invoice_details), 200
    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 400

@bp.route("/invoice/<invoice_id>/details/index.html", methods=["GET"])
def get_invoice_html(invoice_id):
    try:
        from jinja2 import Environment, FileSystemLoader
        from datetime import datetime
        
        invoice_details = PaymentService.get_detailed_invoice(invoice_id)
        if not invoice_details:
            return "Invoice not found", 404
        
        # Add generation timestamp
        invoice_details['generated_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Render HTML template
        env = Environment(loader=FileSystemLoader('templates'))
        template = env.get_template('invoice_template.html')
        html_content = template.render(**invoice_details)
        
        return html_content
    except Exception as e:
        return f"Error: {str(e)}", 400

@bp.route("/outstanding", methods=["GET"])
def get_outstanding_payments():
    """Get all outstanding payments with filters"""
    from payments.payment import Payment
    from invoices.invoice import Invoice
    from customers.customer import Customer
    from decimal import Decimal
    
    # Get query parameters
    customer_id = request.args.get('customer_id')
    status = request.args.get('status', 'all')  # all, pending, partial
    
    # Base query for invoices with outstanding balance
    query = db.session.query(Invoice, Customer).join(Customer)
    
    if customer_id:
        query = query.filter(Invoice.customer_id == customer_id)
    
    if status == 'pending':
        query = query.filter(Invoice.status == 'Pending')
    elif status == 'partial':
        query = query.filter(Invoice.status == 'Partially Paid')
    elif status != 'all':
        query = query.filter(Invoice.status.in_(['Pending', 'Partially Paid']))
    else:
        query = query.filter(Invoice.status.in_(['Pending', 'Partially Paid']))
    
    results = query.all()
    outstanding_list = []
    
    for invoice, customer in results:
        # Calculate outstanding amount
        total_paid = sum(Decimal(p.amount_paid or 0) for p in invoice.payments)
        outstanding = Decimal(invoice.grand_total) - total_paid
        
        if outstanding > 0:
            outstanding_list.append({
                "invoice_id": invoice.id,
                "invoice_number": invoice.invoice_number,
                "customer_id": customer.id,
                "customer_name": customer.contact_person,
                "business_name": customer.business_name,
                "phone": customer.phone,
                "invoice_date": invoice.invoice_date.isoformat(),
                "due_date": invoice.due_date.isoformat() if invoice.due_date else None,
                "grand_total": str(invoice.grand_total),
                "amount_paid": str(total_paid),
                "outstanding_amount": str(outstanding),
                "status": invoice.status,
                "days_overdue": (datetime.now() - invoice.due_date).days if invoice.due_date and datetime.now() > invoice.due_date else 0
            })
    
    return jsonify({
        "outstanding_payments": outstanding_list,
        "total_outstanding": str(sum(Decimal(item['outstanding_amount']) for item in outstanding_list)),
        "count": len(outstanding_list)
    }), 200

@bp.route("/outstanding/customers", methods=["GET"])
def get_customer_wise_outstanding():
    """Get outstanding amounts grouped by customer"""
    from payments.payment import Payment
    from invoices.invoice import Invoice
    from customers.customer import Customer
    from decimal import Decimal
    from sqlalchemy import func
    
    # Query to get customer-wise outstanding
    results = db.session.query(
        Customer.id,
        Customer.contact_person,
        Customer.business_name,
        Customer.phone,
        Customer.email,
        func.sum(Invoice.grand_total).label('total_invoiced'),
        func.count(Invoice.id).label('invoice_count')
    ).join(Invoice).filter(
        Invoice.status.in_(['Pending', 'Partially Paid'])
    ).group_by(
        Customer.id, Customer.contact_person, Customer.business_name, Customer.phone, Customer.email
    ).all()
    
    customer_outstanding = []
    for result in results:
        # Calculate actual outstanding for this customer
        customer_invoices = Invoice.query.filter_by(customer_id=result.id).filter(
            Invoice.status.in_(['Pending', 'Partially Paid'])
        ).all()
        
        total_outstanding = Decimal('0')
        overdue_amount = Decimal('0')
        invoice_details = []
        
        for invoice in customer_invoices:
            total_paid = sum(Decimal(p.amount_paid or 0) for p in invoice.payments)
            outstanding = Decimal(invoice.grand_total) - total_paid
            
            if outstanding > 0:
                total_outstanding += outstanding
                
                # Check if overdue
                is_overdue = invoice.due_date and datetime.now() > invoice.due_date
                if is_overdue:
                    overdue_amount += outstanding
                
                invoice_details.append({
                    "invoice_id": invoice.id,
                    "invoice_number": invoice.invoice_number,
                    "invoice_date": invoice.invoice_date.isoformat(),
                    "due_date": invoice.due_date.isoformat() if invoice.due_date else None,
                    "grand_total": str(invoice.grand_total),
                    "amount_paid": str(total_paid),
                    "outstanding_amount": str(outstanding),
                    "is_overdue": is_overdue,
                    "days_overdue": (datetime.now() - invoice.due_date).days if is_overdue else 0
                })
        
        if total_outstanding > 0:
            customer_outstanding.append({
                "customer_id": result.id,
                "customer_name": result.contact_person,
                "business_name": result.business_name,
                "phone": result.phone,
                "email": result.email,
                "total_outstanding": str(total_outstanding),
                "overdue_amount": str(overdue_amount),
                "invoice_count": len(invoice_details),
                "invoices": invoice_details
            })
    
    return jsonify({
        "customers_with_outstanding": customer_outstanding,
        "total_customers": len(customer_outstanding),
        "grand_total_outstanding": str(sum(Decimal(c['total_outstanding']) for c in customer_outstanding))
    }), 200

@bp.route("/records", methods=["GET"])
def get_payment_records():
    """Enhanced payment records with filtering"""
    from payments.payment import Payment
    from invoices.invoice import Invoice
    from customers.customer import Customer
    from datetime import datetime, timedelta
    
    # Get query parameters
    status = request.args.get('status', 'all')  # all, pending, paid, partial
    customer_id = request.args.get('customer_id')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    search = request.args.get('search', '').strip()
    
    # Build query
    query = db.session.query(Payment, Invoice, Customer).join(
        Invoice, Payment.invoice_id == Invoice.id
    ).join(
        Customer, Payment.customer_id == Customer.id
    )
    
    # Apply filters
    if status != 'all':
        if status == 'pending':
            query = query.filter(Payment.payment_status == 'Pending')
        elif status == 'paid':
            query = query.filter(Payment.payment_status == 'Successful')
        elif status == 'partial':
            query = query.filter(Payment.payment_status == 'Partially Paid')
    
    if customer_id:
        query = query.filter(Payment.customer_id == customer_id)
    
    if date_from:
        query = query.filter(Payment.payment_date >= datetime.fromisoformat(date_from))
    
    if date_to:
        query = query.filter(Payment.payment_date <= datetime.fromisoformat(date_to))
    
    if search:
        query = query.filter(
            db.or_(
                Customer.contact_person.ilike(f'%{search}%'),
                Customer.business_name.ilike(f'%{search}%'),
                Invoice.invoice_number.ilike(f'%{search}%'),
                Payment.transaction_reference.ilike(f'%{search}%')
            )
        )
    
    results = query.order_by(Payment.payment_date.desc()).all()
    
    payment_records = []
    for payment, invoice, customer in results:
        payment_records.append({
            "payment_id": payment.id,
            "invoice_id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "customer_name": customer.contact_person,
            "business_name": customer.business_name,
            "payment_date": payment.payment_date.isoformat(),
            "payment_method": payment.payment_method,
            "amount_before_discount": str(payment.amount_before_discount),
            "discount_amount": str(payment.discount_amount),
            "amount_paid": str(payment.amount_paid),
            "balance_amount": str(payment.balance_amount),
            "payment_status": payment.payment_status,
            "transaction_reference": payment.transaction_reference
        })
    
    return jsonify({
        "payment_records": payment_records,
        "total_records": len(payment_records),
        "filters_applied": {
            "status": status,
            "customer_id": customer_id,
            "date_from": date_from,
            "date_to": date_to,
            "search": search
        }
    }), 200

@bp.route("/reminders", methods=["GET"])
def get_payment_reminders():
    """Get payment reminders for overdue invoices"""
    from invoices.invoice import Invoice
    from customers.customer import Customer
    from decimal import Decimal
    
    # Get overdue invoices
    overdue_invoices = db.session.query(Invoice, Customer).join(Customer).filter(
        Invoice.status.in_(['Pending', 'Partially Paid']),
        Invoice.due_date < datetime.now()
    ).order_by(Invoice.due_date.asc()).all()
    
    reminders = []
    for invoice, customer in overdue_invoices:
        total_paid = sum(Decimal(p.amount_paid or 0) for p in invoice.payments)
        outstanding = Decimal(invoice.grand_total) - total_paid
        days_overdue = (datetime.now() - invoice.due_date).days
        
        if outstanding > 0:
            reminders.append({
                "invoice_id": invoice.id,
                "invoice_number": invoice.invoice_number,
                "customer_id": customer.id,
                "customer_name": customer.contact_person,
                "business_name": customer.business_name,
                "phone": customer.phone,
                "email": customer.email,
                "invoice_date": invoice.invoice_date.isoformat(),
                "due_date": invoice.due_date.isoformat(),
                "grand_total": str(invoice.grand_total),
                "amount_paid": str(total_paid),
                "outstanding_amount": str(outstanding),
                "days_overdue": days_overdue,
                "urgency": "High" if days_overdue > 30 else "Medium" if days_overdue > 15 else "Low"
            })
    
    return jsonify({
        "payment_reminders": reminders,
        "total_overdue": len(reminders),
        "total_amount_overdue": str(sum(Decimal(r['outstanding_amount']) for r in reminders))
    }), 200

@bp.route("/receipt/<payment_id>", methods=["GET"])
def generate_receipt(payment_id):
    """Generate payment receipt"""
    try:
        receipt_data = PaymentService.generate_payment_receipt(payment_id)
        if not receipt_data:
            return jsonify({"error": "Payment not found"}), 404
        return jsonify(receipt_data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@bp.route("/summary", methods=["GET"])
def get_payment_summary():
    """Get payment summary statistics"""
    try:
        summary = PaymentService.get_outstanding_summary()
        return jsonify(summary), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400
