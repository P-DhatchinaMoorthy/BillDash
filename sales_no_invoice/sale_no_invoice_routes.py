from flask import Blueprint, request, jsonify
from extensions import db
from sales_no_invoice.sale_no_invoice_service import SaleNoInvoiceService
from user.auth_bypass import require_permission

bp = Blueprint("sales_no_invoice", __name__)

@bp.route("/", methods=["POST"])
@require_permission('sales', 'write')
def create_sale_no_invoice():
    payload = request.get_json() or {}
    product_id = payload.get("product_id")
    quantity = payload.get("quantity")
    discount_percentage = payload.get("discount_percentage", 0)
    payment_method = payload.get("payment_method")
    if not product_id or not quantity or not payment_method:
        return jsonify({"error": "product_id, quantity and payment_method required"}), 400
    try:
        sale = SaleNoInvoiceService.create_sale(product_id, quantity, discount_percentage, payment_method, notes=payload.get("notes"))
        return jsonify({
            "sale_id": sale.id,
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
@require_permission('sales', 'read')
def list_sales_no_invoice():
    from sales_no_invoice.sale_no_invoice import SaleNoInvoice
    sales = SaleNoInvoice.query.all()
    return jsonify([{
        "id": s.id,
        "product_id": s.product_id,
        "product_name": s.product.product_name if s.product else None,
        "sku": s.product.sku if s.product else None,
        "category": s.product.category.name if s.product and s.product.category else None,
        "subcategory_id": s.product.subcategory_id if s.product and s.product.subcategory_id else None,
        "quantity": s.quantity,
        "selling_price": str(s.selling_price),
        "total_amount": str(s.total_amount),
        "discount_percentage": str(s.discount_percentage),
        "amount_after_discount": str(s.amount_after_discount),
        "payment_method": s.payment_method,
        "sale_date": s.sale_date.isoformat(),
        "notes": s.notes
    } for s in sales]), 200

@bp.route("/<sale_id>", methods=["GET"])
@require_permission('sales', 'read')
def get_sale_no_invoice(sale_id):
    from sales_no_invoice.sale_no_invoice import SaleNoInvoice
    s = SaleNoInvoice.query.get(sale_id)
    if not s:
        return jsonify({"error": "empty"}), 404
    return jsonify({
        "id": s.id,
        "product_id": s.product_id,
        "product_name": s.product.product_name if s.product else None,
        "product_description": s.product.description if s.product else None,
        "sku": s.product.sku if s.product else None,
        "category": s.product.category.name if s.product and s.product.category else None,
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
@require_permission('sales', 'write')
def update_sale_no_invoice(sale_id):
    from sales_no_invoice.sale_no_invoice import SaleNoInvoice
    s = SaleNoInvoice.query.get(sale_id)
    if not s:
        return jsonify({"error": "empty"}), 404
    data = request.get_json() or {}
    s.notes = data.get("notes", s.notes)
    db.session.commit()
    return jsonify({"id": s.id, "notes": s.notes}), 200
