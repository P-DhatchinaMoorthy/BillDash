from flask import Blueprint, request, jsonify, send_file, make_response
from src.extensions import db
from customers.customer import Customer
from user.enhanced_auth_middleware import require_permission_jwt
from user.audit_logger import audit_decorator
import pandas as pd
import io
import os
from werkzeug.utils import secure_filename
from datetime import datetime

bp = Blueprint("customers", __name__)


# --- CORS for all responses ---
@bp.after_request
def add_cors_headers(response):
    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers.add("Access-Control-Allow-Headers", "Content-Type,Authorization")
    response.headers.add("Access-Control-Allow-Methods", "GET,PUT,POST,DELETE,OPTIONS")
    return response


@bp.before_request
def handle_options():
    if request.method == "OPTIONS":
        return make_response("", 204)


# -------------------- CREATE CUSTOMER --------------------
@bp.route("/", methods=["POST", "OPTIONS"])
@require_permission_jwt('customers', 'write')
@audit_decorator('customers', 'CREATE', 'customer')
def create_customer():
    if request.content_type and 'multipart/form-data' in request.content_type:
        data = request.form.to_dict()
        uploaded_file = request.files.get('document')
    else:
        data = request.get_json() or {}
        uploaded_file = None

    if not data.get("phone"):
        return jsonify({"error": "phone is required"}), 400
    if Customer.query.filter_by(phone=data.get("phone")).first():
        return jsonify({"error": "phone already exists"}), 400

    try:
        cust = Customer(
            contact_person=data.get("contact_person"),
            business_name=data.get("business_name"),
            email=data.get("email"),
            phone=data.get("phone"),
            branch=data.get("branch"),
            alternate_phone=data.get("alternate_phone"),
            billing_address=data.get("billing_address"),
            shipping_address=data.get("shipping_address"),
            gst_number=data.get("gst_number"),
            pan_number=data.get("pan_number"),
            payment_terms=data.get("payment_terms"),
            opening_balance=data.get("opening_balance", 0),
            notes=data.get("notes"),
        )
        db.session.add(cust)
        db.session.flush()  # get ID

        # Handle file upload
        if uploaded_file and uploaded_file.filename:
            upload_base = "uploads"
            customer_folder = os.path.join(upload_base, "customers", str(cust.id))
            os.makedirs(customer_folder, exist_ok=True)

            filename = secure_filename(uploaded_file.filename)
            file_path = os.path.join(customer_folder, filename)
            uploaded_file.save(file_path)

            cust.document_path = f"customers/{cust.id}/{filename}"

        db.session.commit()
        return jsonify({
            "id": cust.id,
            "contact_person": cust.contact_person,
            "phone": cust.phone,
            "document_path": getattr(cust, 'document_path', None)
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400


# -------------------- LIST CUSTOMERS --------------------
@bp.route("/", methods=["GET", "OPTIONS"])
@require_permission_jwt('customers', 'read')
def list_customers():
    page = int(request.args.get('page', 1))
    per_page = 10
    id_from = request.args.get('id_from')
    id_to = request.args.get('id_to')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    phone = request.args.get('phone')

    q = Customer.query

    if id_from:
        q = q.filter(Customer.id >= int(id_from))
    if id_to:
        q = q.filter(Customer.id <= int(id_to))
    if date_from:
        try:
            dt_from = datetime.fromisoformat(date_from)
            q = q.filter(Customer.created_at >= dt_from)
        except ValueError:
            return jsonify({"error": "Invalid date_from format, use YYYY-MM-DD"}), 400
    if date_to:
        try:
            dt_to = datetime.fromisoformat(date_to)
            q = q.filter(Customer.created_at <= dt_to)
        except ValueError:
            return jsonify({"error": "Invalid date_to format, use YYYY-MM-DD"}), 400
    if phone:
        q = q.filter((Customer.phone == phone) | (Customer.alternate_phone == phone))

    paginated = q.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        "customers": [{
            "id": c.id,
            "contact_person": c.contact_person,
            "business_name": c.business_name,
            "email": c.email,
            "phone": c.phone,
            "alternate_phone": c.alternate_phone,
            "billing_address": c.billing_address,
            "shipping_address": c.shipping_address,
            "gst_number": c.gst_number,
            "pan_number": c.pan_number,
            "branch": c.branch,
            "document_path": getattr(c, 'document_path', None),
            "payment_terms": c.payment_terms,
            "opening_balance": str(c.opening_balance),
            "notes": c.notes,
            "created_at": c.created_at.isoformat(),
            "updated_at": c.updated_at.isoformat() if c.updated_at else None
        } for c in paginated.items],
        "pagination": {
            "page": paginated.page,
            "per_page": paginated.per_page,
            "total": paginated.total,
            "pages": paginated.pages,
            "has_next": paginated.has_next,
            "has_prev": paginated.has_prev
        }
    }), 200


# -------------------- GET CUSTOMER --------------------
@bp.route("/<customer_id>", methods=["GET", "OPTIONS"])
@require_permission_jwt('customers', 'read')
def get_customer(customer_id):
    try:
        customer_id = int(customer_id)
    except ValueError:
        return jsonify({"error": "Invalid customer ID"}), 400

    c = Customer.query.get(customer_id)
    if not c:
        return jsonify({"error": "empty"}), 404
    return jsonify({
        "id": c.id,
        "contact_person": c.contact_person,
        "business_name": c.business_name,
        "email": c.email,
        "phone": c.phone,
        "alternate_phone": c.alternate_phone,
        "branch": c.branch,
        "document_path": getattr(c, 'document_path', None),
        "billing_address": c.billing_address,
        "shipping_address": c.shipping_address,
        "gst_number": c.gst_number,
        "pan_number": c.pan_number,
        "payment_terms": c.payment_terms,
        "opening_balance": str(c.opening_balance),
        "notes": c.notes,
        "created_at": c.created_at.isoformat(),
        "updated_at": c.updated_at.isoformat() if c.updated_at else None
    }), 200


# -------------------- UPDATE CUSTOMER --------------------
@bp.route("/<customer_id>", methods=["PUT", "OPTIONS"])
@require_permission_jwt('customers', 'write')
@audit_decorator('customers', 'UPDATE', 'customer')
def update_customer(customer_id):
    try:
        customer_id = int(customer_id)
    except ValueError:
        return jsonify({"error": "Invalid customer ID"}), 400

    c = Customer.query.get(customer_id)
    if not c:
        return jsonify({"error": "empty"}), 404
    data = request.get_json() or {}
    if "phone" in data and data["phone"] != c.phone:
        if Customer.query.filter_by(phone=data["phone"]).first():
            return jsonify({"error": "phone already exists"}), 400
    try:
        for field in [
            "contact_person", "business_name", "phone", "email", "alternate_phone",
            "billing_address", "shipping_address", "gst_number", "branch",
            "pan_number", "payment_terms", "opening_balance", "notes"
        ]:
            if field in data:
                setattr(c, field, data[field])
        db.session.commit()
        return jsonify({"id": c.id, "contact_person": c.contact_person}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400


# -------------------- GET CUSTOMER INVOICES --------------------
@bp.route("/<customer_id>/invoices", methods=["GET", "OPTIONS"])
def get_customer_invoices(customer_id):
    try:
        customer_id = int(customer_id)
    except ValueError:
        return jsonify({"error": "Invalid customer ID"}), 400

    customer = Customer.query.get(customer_id)
    if not customer:
        return jsonify({"error": "Customer not found"}), 404

    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 10))
    payment_status_filter = request.args.get('payment_status')

    try:
        from invoices.invoice import Invoice
        from payments.payment import Payment
        
        invoices_query = Invoice.query.filter_by(customer_id=customer_id)
        paginated = invoices_query.paginate(page=page, per_page=per_page, error_out=False)
        
        invoices_list = []
        for invoice in paginated.items:
            payment = Payment.query.filter_by(invoice_id=invoice.id).first()
            payment_status = "pending"
            if payment and payment.payment_status.lower() == "paid":
                payment_status = "paid"
            
            # Apply payment status filter
            if payment_status_filter and payment_status != payment_status_filter.lower():
                continue
            
            # Get invoice items with product details
            from invoices.invoice_item import InvoiceItem
            from products.product import Product
            
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
            
            invoices_list.append({
                "invoice_id": invoice.id,
                "invoice_number": invoice.invoice_number,
                "customer_id": invoice.customer_id,
                "invoice_date": invoice.invoice_date.strftime("%Y-%m-%d"),
                "due_date": invoice.due_date.strftime("%Y-%m-%d") if invoice.due_date else None,
                "total_before_tax": str(invoice.total_before_tax),
                "tax_amount": str(invoice.tax_amount),
                "cgst_amount": str(getattr(invoice, 'cgst_amount', 0)),
                "sgst_amount": str(getattr(invoice, 'sgst_amount', 0)),
                "igst_amount": str(getattr(invoice, 'igst_amount', 0)),
                "discount_amount": str(invoice.discount_amount),
                "shipping_charges": str(invoice.shipping_charges),
                "other_charges": str(invoice.other_charges),
                "additional_discount": str(getattr(invoice, 'additional_discount', 0)),
                "grand_total": str(invoice.grand_total),
                "payment_terms": invoice.payment_terms,
                "currency": invoice.currency,
                "status": invoice.status,
                "notes": invoice.notes,
                "payment_status": payment_status,
                "payment_id": payment.id if payment else None,
                "items": items,
                "total_items": len(items),
                "created_at": invoice.created_at.isoformat(),
                "updated_at": invoice.updated_at.isoformat() if invoice.updated_at else None
            })
        
        return jsonify({
            "customer": {
                "id": customer.id,
                "business_name": customer.business_name,
                "contact_person": customer.contact_person
            },
            "invoices": invoices_list,
            "pagination": {
                "page": paginated.page,
                "per_page": paginated.per_page,
                "total": paginated.total,
                "pages": paginated.pages
            }
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# -------------------- EXPORT CUSTOMERS --------------------
@bp.route("/export", methods=["GET", "OPTIONS"])
@require_permission_jwt('customers', 'read')
def export_customers():
    try:
        format_type = request.args.get('format', 'csv').lower()
        customers = Customer.query.all()

        data = [{
            'id': c.id,
            'contact_person': c.contact_person,
            'business_name': c.business_name or '',
            'email': c.email or '',
            'phone': c.phone,
            'alternate_phone': c.alternate_phone or '',
            'billing_address': c.billing_address or '',
            'shipping_address': c.shipping_address or '',
            'gst_number': c.gst_number or '',
            "branch": c.branch or '',
            'document_path': getattr(c, 'document_path', ''),
            'pan_number': c.pan_number or '',
            'payment_terms': c.payment_terms or '',
            'opening_balance': float(c.opening_balance) if c.opening_balance else 0,
            'notes': c.notes or '',
            'created_at': c.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'updated_at': c.updated_at.strftime('%Y-%m-%d %H:%M:%S') if c.updated_at else ''
        } for c in customers]

        df = pd.DataFrame(data)

        if format_type == 'excel':
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Customers', index=False)
            output.seek(0)
            return send_file(
                output,
                as_attachment=True,
                download_name='customers_export.xlsx',
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
        else:
            output = io.StringIO()
            df.to_csv(output, index=False)
            response = make_response(output.getvalue())
            response.headers['Content-Type'] = 'text/csv; charset=utf-8'
            response.headers['Content-Disposition'] = 'attachment; filename=customers_export.csv'
            return response

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# -------------------- BULK IMPORT --------------------
@bp.route("/bulk-import", methods=["POST", "OPTIONS"])
def bulk_import_customers():
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No file uploaded"}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "No file selected"}), 400

        if file.filename.endswith('.csv'):
            df = pd.read_csv(io.StringIO(file.read().decode('utf-8')))
        elif file.filename.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(io.BytesIO(file.read()))
        else:
            return jsonify({"error": "Only CSV and Excel files supported"}), 400

        required_cols = ['contact_person', 'phone']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            return jsonify({"error": f"Missing columns: {missing_cols}"}), 400

        results, success_count = Customer.bulk_import(df)

        return jsonify({
            "success_count": success_count,
            "total_rows": len(df),
            "results": results
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/<customer_id>", methods=["DELETE", "OPTIONS"])
@require_permission_jwt('customers', 'write')
@audit_decorator('customers', 'DELETE', 'customer')
def delete_customer(customer_id):
    try:
        customer_id = int(customer_id)
    except ValueError:
        return jsonify({"error": "Invalid customer ID"}), 400

    c = Customer.query.get(customer_id)
    if not c:
        return jsonify({"error": "Customer not found"}), 404
    
    try:
        db.session.delete(c)
        db.session.commit()
        return jsonify({"message": "Customer deleted successfully"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400