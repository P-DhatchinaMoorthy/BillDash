# routes/sales_routes.py
from flask import Blueprint, request, jsonify
from sales.sales_service import SalesService
from user.auth_bypass import require_permission

bp = Blueprint("sales", __name__)

@bp.route("/create-with-payment", methods=["POST"])
@require_permission('sales', 'write')
def create_sale_with_payment():
    payload = request.get_json() or {}
    customer_id = payload.get("customer_id")
    items = payload.get("items")  # [{"product_id": "uuid", "quantity": 2}]
    payment_method = payload.get("payment_method")
    payment_amount = payload.get("payment_amount")
    
    if not customer_id or not items or not payment_method or payment_amount is None:
        return jsonify({"error": "customer_id, items, payment_method, payment_amount required"}), 400
    
    try:
        result = SalesService.create_sale_with_payment(
            customer_id=customer_id,
            items=items,
            payment_method=payment_method,
            payment_amount=payment_amount,
            discount_percentage=payload.get("discount_percentage", 0),
            bank_details=payload.get("bank_details"),
            transaction_reference=payload.get("transaction_reference")
        )
        return jsonify(result), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400