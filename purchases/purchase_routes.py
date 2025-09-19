from flask import Blueprint, request, jsonify
from purchases.purchase_service import PurchaseService
from user.enhanced_auth_middleware import require_permission_jwt
from user.audit_logger import audit_decorator
from src.extensions import db

bp = Blueprint("purchases", __name__)


@bp.route("/add-stock", methods=["POST"])
@require_permission_jwt('purchases', 'write')
@audit_decorator('purchases', 'ADD_STOCK')
def add_stock_from_supplier():
    payload = request.get_json() or {}
    products = payload.get("products")
    supplier_id = payload.get("supplier_id")

    # Support both old format (single product) and new format (multiple products)
    if not products:
        # Old format - single product
        product_id = payload.get("product_id")
        quantity = payload.get("quantity")
        if not product_id or not quantity:
            return jsonify({"error": "products array or product_id, quantity required"}), 400
        products = [{"product_id": product_id, "quantity": quantity}]

    if not supplier_id:
        return jsonify({"error": "supplier_id required"}), 400

    # Validate supplier exists
    from suppliers.supplier import Supplier
    supplier = Supplier.query.get(supplier_id)
    if not supplier:
        return jsonify({"error": f"Supplier with ID {supplier_id} not found"}), 400

    try:
        result = PurchaseService.add_multiple_stock_from_supplier(
            products=products,
            supplier_id=supplier_id,
            reference_number=payload.get("reference_number"),
            notes=payload.get("notes"),
            total_amount=payload.get("total_amount"),
            payment_amount=payload.get("payment_amount", 0),
            payment_method=payload.get("payment_method"),
            transaction_reference=payload.get("transaction_reference")
        )
        return jsonify(result), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/update-payment/<int:purchase_id>", methods=["PUT"])
@require_permission_jwt('purchases', 'write')
@audit_decorator('purchases', 'UPDATE_PAYMENT')
def update_purchase_payment(purchase_id):
    payload = request.get_json() or {}
    payment_amount = payload.get("payment_amount")

    if payment_amount is None:
        return jsonify({"error": "payment_amount required"}), 400

    try:
        result = PurchaseService.update_payment(
            purchase_id=purchase_id,
            payment_amount=payment_amount,
            payment_method=payload.get("payment_method"),
            transaction_reference=payload.get("transaction_reference")
        )
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@bp.route("/<int:purchase_id>", methods=["DELETE"])
@require_permission_jwt('purchases', 'write')
@audit_decorator('purchases', 'DELETE')
def delete_purchase(purchase_id):
    from stock_transactions.stock_transaction import StockTransaction
    p = StockTransaction.query.get(purchase_id)
    if not p:
        return jsonify({"error": "Purchase not found"}), 404
    
    try:
        db.session.delete(p)
        db.session.commit()
        return jsonify({"message": "Purchase deleted successfully"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400