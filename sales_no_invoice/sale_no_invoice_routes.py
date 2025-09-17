from flask import Blueprint, request, jsonify, send_file, make_response
from src.extensions import db
from sales_no_invoice.sale_no_invoice_service import SaleNoInvoiceService
from user.enhanced_auth_middleware import require_permission_jwt
from user.audit_logger import audit_decorator
import pandas as pd
import io
from datetime import datetime

bp = Blueprint("sales_no_invoice", __name__)

@bp.route("/", methods=["POST"])
@require_permission_jwt('sales', 'write')
@audit_decorator('sales', 'NO_INVOICE_SALE')
def create_sale_no_invoice():
    payload = request.get_json() or {}
    product_id = payload.get("product_id")
    quantity = payload.get("quantity")
    discount_percentage = payload.get("discount_percentage", 0)
    customer_id = payload.get("customer_id")
    payment_method = payload.get("payment_method")
    if not product_id or not quantity or not payment_method:
        return jsonify({"error": "product_id, quantity and payment_method required"}), 400
    try:
        sale = SaleNoInvoiceService.create_sale(product_id, quantity, discount_percentage, payment_method, customer_id, notes=payload.get("notes"))
        return jsonify({
            "sale_id": sale.id,
            "customer_id": sale.customer_id,
            "product_name": sale.product.product_name,
            "product_details": {
                "id": sale.product.id,
                "name": sale.product.product_name,
                "sku": sale.product.sku,
                "selling_price": str(sale.product.selling_price)
            },
            "quantity": sale.quantity,
            "total_amount": str(sale.total_amount),
            "discount_percentage": str(sale.discount_percentage),
            "discount_amount": str(sale.discount_amount),
            "amount_after_discount": str(sale.amount_after_discount),
            "payment_method": sale.payment_method
        }), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@bp.route("/", methods=["GET"])
@require_permission_jwt('sales', 'read')
def list_sales_no_invoice():
    from sales_no_invoice.sale_no_invoice import SaleNoInvoice
    from customers.customer import Customer
    sales = SaleNoInvoice.query.all()
    result = []
    for s in sales:
        customer = Customer.query.get(s.customer_id) if s.customer_id else None

        result.append({
            "id": s.id,
            "customer_id": s.customer_id,
            "customer_name": customer.contact_person if customer else None,
            "business_name": customer.business_name if customer else None,
            "email": customer.email if customer else None,
            "phone": customer.phone if customer else None,
            "product_id": s.product_id,
            "product_name": s.product.product_name if s.product else None,
            "sku": s.product.sku if s.product else None,
            "subcategory_id": s.product.subcategory_id if s.product and s.product.subcategory_id else None,
            "quantity": s.quantity,
            "selling_price": str(s.selling_price),
            "total_amount": str(s.total_amount),
            "discount_percentage": str(s.discount_percentage),
            "amount_after_discount": str(s.amount_after_discount),
            "payment_method": s.payment_method,
            "sale_date": s.sale_date.isoformat(),
            "notes": s.notes
        })
    return jsonify(result), 200

@bp.route("/<sale_id>", methods=["GET"])
@require_permission_jwt('sales', 'read')
def get_sale_no_invoice(sale_id):
    from sales_no_invoice.sale_no_invoice import SaleNoInvoice
    from customers.customer import Customer
    s = SaleNoInvoice.query.get(sale_id)
    if not s:
        return jsonify({"error": "empty"}), 404
    customer = Customer.query.get(s.customer_id) if s.customer_id else None
    return jsonify({
        "id": s.id,
        "customer_id": s.customer_id,
        "customer_name": customer.contact_person if customer else None,
        "business_name": customer.business_name if customer else None,
        "email": customer.email if customer else None,
        "phone": customer.phone if customer else None,
        "product_id": s.product_id,
        "product_name": s.product.product_name if s.product else None,
        "product_description": s.product.description if s.product else None,
        "sku": s.product.sku if s.product else None,
        # "category": s.product.category.name if s.product and s.product.category else None,
        #"subcategory": s.product.subcategory.name if s.product and s.product.subcategory else None,
        "unit_of_measure": s.product.unit_of_measure if s.product else None,
        "unit_price": str(s.product.selling_price) if s.product else "0.00",
        "purchase_price": str(s.product.purchase_price) if s.product else "0.00",
        "quantity_in_stock": s.product.quantity_in_stock if s.product else 0,
        "reorder_level": s.product.reorder_level if s.product else None,
        "max_stock_level": s.product.max_stock_level if s.product else None,
        "supplier_id": s.product.supplier_id if s.product else None,
        "batch_number": s.product.batch_number if s.product else None,
        "expiry_date": s.product.expiry_date.isoformat() if s.product and s.product.expiry_date else None,
        "barcode": s.product.barcode if s.product else None,
        "quantity": s.quantity,
        "selling_price": str(s.selling_price),
        "total_amount": str(s.total_amount),
        "sale_date": s.sale_date.isoformat(),
        "discount_percentage": str(s.discount_percentage),
        "discount_amount": str(s.discount_amount),
        "amount_after_discount": str(s.amount_after_discount),
        "payment_method": s.payment_method,
        "notes": s.notes
    }), 200

@bp.route("/<sale_id>", methods=["PUT"])
@require_permission_jwt('sales', 'write')
@audit_decorator('sales', 'UPDATE')
def update_sale_no_invoice(sale_id):
    from sales_no_invoice.sale_no_invoice import SaleNoInvoice
    s = SaleNoInvoice.query.get(sale_id)
    if not s:
        return jsonify({"error": "empty"}), 404
    data = request.get_json() or {}
    s.notes = data.get("notes", s.notes)
    db.session.commit()
    return jsonify({"id": s.id, "notes": s.notes}), 200


@bp.route("/export", methods=["GET"])
@require_permission_jwt('sales', 'read')
def export_sales_no_invoice():
    try:
        format_type = request.args.get('format', 'csv').lower()
        
        from sales_no_invoice.sale_no_invoice import SaleNoInvoice
        from customers.customer import Customer
        
        sales = SaleNoInvoice.query.all()
        data = []
        
        for s in sales:
            customer = Customer.query.get(s.customer_id) if s.customer_id else None
            
            data.append({
                "Sale ID": s.id,
                "Customer ID": s.customer_id or '',
                "Customer Name": customer.contact_person if customer else '',
                "Business Name": customer.business_name if customer else '',
                "Email": customer.email if customer else '',
                "Phone": customer.phone if customer else '',
                "Product ID": s.product_id,
                "Product Name": s.product.product_name if s.product else '',
                "SKU": s.product.sku if s.product else '',
                "Quantity": s.quantity,
                "Selling Price": float(s.selling_price),
                "Total Amount": float(s.total_amount),
                "Discount Percentage": float(s.discount_percentage),
                "Discount Amount": float(s.discount_amount or 0),
                "Amount After Discount": float(s.amount_after_discount),
                "Payment Method": s.payment_method,
                "Sale Date": s.sale_date.strftime('%Y-%m-%d %H:%M:%S'),
                "Notes": s.notes or ''
            })
        
        df = pd.DataFrame(data)
        
        if format_type == 'excel':
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Sales No Invoice', index=False)
            output.seek(0)
            
            return send_file(
                output,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name=f'sales_no_invoice_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
            )
        else:
            output = io.StringIO()
            df.to_csv(output, index=False)
            response = make_response(output.getvalue())
            response.headers['Content-Type'] = 'text/csv; charset=utf-8'
            response.headers['Content-Disposition'] = f'attachment; filename=sales_no_invoice_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
            return response
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500
@bp.route("/<int:sale_id>", methods=["DELETE"])
@require_permission_jwt('sales', 'write')
@audit_decorator('sales', 'DELETE')
def delete_sale_no_invoice(sale_id):
    from sales_no_invoice.sale_no_invoice import SaleNoInvoice
    s = SaleNoInvoice.query.get(sale_id)
    if not s:
        return jsonify({"error": "Sale not found"}), 404
    
    try:
        db.session.delete(s)
        db.session.commit()
        return jsonify({"message": "Sale deleted successfully"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400