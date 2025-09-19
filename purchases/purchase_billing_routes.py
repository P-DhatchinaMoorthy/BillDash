from flask import Blueprint, request, jsonify, render_template, send_file, make_response
from purchases.purchase_billing_service import PurchaseBillingService
from purchases.purchase_service import PurchaseService
from purchases.purchase_bill import PurchaseBill
from decimal import Decimal
from user.enhanced_auth_middleware import require_permission_jwt
from user.audit_logger import audit_decorator
import json
from jinja2 import Environment, FileSystemLoader
import pandas as pd
import io
from datetime import datetime

bp = Blueprint("purchase_billing", __name__)

@bp.route("/damage", methods=["POST"])
@bp.route("/damage/", methods=["POST"])
@require_permission_jwt('purchases', 'write')
@audit_decorator('purchases', 'DAMAGE_RECORD')
def create_damage_record():
    from src.extensions import db
    from purchases.supplier_damage import SupplierDamage
    from products.product import Product
    
    try:
        data = request.get_json(force=True)
    except Exception as e:
        return jsonify({"error": f"Invalid JSON: {str(e)}"}), 400
    
    if not data:
        data = {}
    required = ["purchase_id", "supplier_id", "product_id", "quantity_damaged", "damage_type"]
    if not all(field in data for field in required):
        return jsonify({"error": f"Required fields: {required}"}), 400

    try:
        product = Product.query.get(data["product_id"])
        if not product:
            return jsonify({"error": "Product not found"}), 400
        
        quantity_damaged = data["quantity_damaged"]
        damage_type = data["damage_type"]
        
        # Calculate refund amount
        refund_amount = 0
        if damage_type == "refund":
            if product.quantity_in_stock < quantity_damaged:
                return jsonify({"error": f"Insufficient stock. Available: {product.quantity_in_stock}, Requested: {quantity_damaged}"}), 400
            product.quantity_in_stock -= quantity_damaged
            refund_amount = product.purchase_price * quantity_damaged
        
        # For replacement: no stock change (just record the damage)
        
        from datetime import datetime
        
        # Set supplier response and dates based on damage type
        supplier_response = "Refunded" if damage_type == "refund" else "Replaced"
        replacement_date = datetime.utcnow() if damage_type == "replacement" else None
        replacement_quantity = quantity_damaged if damage_type == "replacement" else 0
        
        total_amount = product.purchase_price * quantity_damaged
        
        damage = SupplierDamage(
            purchase_id=data["purchase_id"],
            supplier_id=data["supplier_id"],
            product_id=data["product_id"],
            quantity_damaged=quantity_damaged,
            damage_type=damage_type,
            damage_reason=data.get("damage_reason"),
            unit_price=product.purchase_price,
            total_amount=total_amount,
            refund_amount=refund_amount,
            status="Paid" if damage_type == "refund" else "Replaced",
            supplier_response=supplier_response,
            replacement_quantity=replacement_quantity,
            replacement_date=replacement_date,
            notes=data.get("notes")
        )
        
        db.session.add(damage)
        db.session.commit()
        
        if damage_type == "refund":
            result = {
                "success": True,
                "message": "Damage refund processed successfully",
                "damage_record": {
                    "damage_id": damage.id,
                    "damage_number": damage.damage_number,
                    "status": damage.status,
                    "refund_amount": str(damage.refund_amount)
                },
                "inventory_impact": {
                    "stock_reduced": True,
                    "quantity_returned": quantity_damaged,
                    "new_stock_level": product.quantity_in_stock
                }
            }
        else:
            result = {
                "success": True,
                "message": "Replacement request submitted successfully",
                "damage_record": {
                    "damage_id": damage.id,
                    "damage_number": damage.damage_number,
                    "status": damage.status,
                    "replacement_quantity": quantity_damaged
                },
                "inventory_impact": {
                    "stock_reduced": False,
                    "awaiting_replacement": True,
                    "current_stock_level": product.quantity_in_stock
                }
            }
        
        return jsonify(result), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/damage", methods=["GET"])
@bp.route("/damage/", methods=["GET"])
@require_permission_jwt('purchases', 'read')
def list_damage_records():
    from purchases.supplier_damage import SupplierDamage
    from products.product import Product
    
    damages = SupplierDamage.query.all()
    result = []
    
    for damage in damages:
        product = Product.query.get(damage.product_id) if damage.product_id else None
        result.append({
            "damage_id": damage.id,
            "damage_number": damage.damage_number,
            "product_id": damage.product_id,
            "product_name": product.product_name if product else "Unknown",
            "quantity_damaged": damage.quantity_damaged,
            "damage_date": damage.damage_date.isoformat(),
            "damage_reason": damage.damage_reason,
            "damage_type": damage.damage_type,
            "status": damage.status,
            "refund_amount": str(damage.refund_amount) if damage.refund_amount else "0.00",
            "total_amount": str(damage.total_amount)
        })
    
    return jsonify(result), 200


@bp.route("/damage/<int:damage_id>", methods=["GET"])
@require_permission_jwt('purchases', 'read')
def get_damage_details(damage_id):
    from purchases.supplier_damage import SupplierDamage
    from products.product import Product
    
    damage = SupplierDamage.query.get(damage_id)
    if not damage:
        return jsonify({"error": "Damage record not found"}), 404
    
    product = Product.query.get(damage.product_id) if damage.product_id else None
    
    return jsonify({
        "damage_id": damage.id,
        "damage_number": damage.damage_number,
        "product": {
            "id": product.id,
            "name": product.product_name,
            "sku": product.sku,
            "purchase_price": str(product.purchase_price) if product.purchase_price else "0.00"
        } if product else None,
        "damage_details": {
            "quantity_damaged": damage.quantity_damaged,
            "damage_reason": damage.damage_reason,
            "damage_type": damage.damage_type,
            "damage_date": damage.damage_date.isoformat()
        },
        "financial_details": {
            "unit_price": str(damage.unit_price),
            "total_amount": str(damage.total_amount),
            "refund_amount": str(damage.refund_amount),
            "replacement_quantity": damage.replacement_quantity
        },
        "status_info": {
            "status": damage.status,
            "supplier_response": damage.supplier_response,
            "replacement_date": damage.replacement_date.isoformat() if damage.replacement_date else None
        },
        "timestamps": {
            "created_at": damage.created_at.isoformat(),
            "updated_at": damage.updated_at.isoformat() if damage.updated_at else None
        },
        "notes": damage.notes
    }), 200


@bp.route("/return", methods=["POST"])
@bp.route("/return/", methods=["POST"])
@require_permission_jwt('purchases', 'write')
@audit_decorator('purchases', 'RETURN_STOCK')
def return_stock_to_supplier():
    from src.extensions import db
    from stock_transactions.stock_transaction import StockTransaction
    from products.product import Product
    
    try:
        data = request.get_json(force=True)
    except Exception as e:
        return jsonify({"error": f"Invalid JSON: {str(e)}"}), 400
    
    required = ["purchase_id", "supplier_id", "product_id", "quantity"]
    if not all(field in data for field in required):
        return jsonify({"error": f"Required fields: {required}"}), 400

    try:
        product = Product.query.get(data["product_id"])
        if not product:
            return jsonify({"error": "Product not found"}), 400
        
        quantity = int(data["quantity"])
        if product.quantity_in_stock < quantity:
            return jsonify({"error": f"Insufficient stock. Available: {product.quantity_in_stock}, Requested: {quantity}"}), 400
        
        product.quantity_in_stock -= quantity
        return_amount = product.purchase_price * quantity
        
        return_transaction = StockTransaction(
            product_id=data["product_id"],
            transaction_type="Return",
            quantity=-quantity,
            supplier_id=data["supplier_id"],
            reference_number=f"RET-{data['purchase_id']}-{quantity}",
            notes=data.get("notes", "")
        )
        
        db.session.add(return_transaction)
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "Stock returned to supplier successfully",
            "return_details": {
                "return_id": return_transaction.id,
                "reference_number": return_transaction.reference_number,
                "product_id": data["product_id"],
                "product_name": product.product_name,
                "quantity_returned": quantity,
                "return_amount": str(return_amount),
                "supplier_owes_us": str(return_amount)
            },
            "inventory_impact": {
                "stock_reduced": True,
                "new_stock_level": product.quantity_in_stock
            }
        }), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/return", methods=["GET"])
@bp.route("/return/", methods=["GET"])
@require_permission_jwt('purchases', 'read')
def list_stock_returns():
    from stock_transactions.stock_transaction import StockTransaction
    from suppliers.supplier import Supplier
    from products.product import Product
    
    returns = StockTransaction.query.filter(
        StockTransaction.transaction_type == 'Return',
        StockTransaction.supplier_id.isnot(None)
    ).all()
    result = []
    
    for ret in returns:
        supplier = Supplier.query.get(ret.supplier_id) if ret.supplier_id else None
        product = Product.query.get(ret.product_id) if ret.product_id else None
        
        return_amount = abs(ret.quantity) * product.purchase_price if product else 0
        
        result.append({
            "return_id": ret.id,
            "reference_number": ret.reference_number,
            "supplier_id": ret.supplier_id,
            "supplier_name": supplier.name if supplier else None,
            "product_id": ret.product_id,
            "product_name": product.product_name if product else None,
            "quantity_returned": abs(ret.quantity),
            "return_amount": str(return_amount),
            "supplier_owes_us": str(return_amount),
            "return_date": ret.transaction_date.isoformat(),
            "notes": ret.notes
        })
    
    return jsonify(result), 200


@bp.route("/", methods=["GET"])
@require_permission_jwt('purchases', 'read')
def list_purchase_bills():
    from stock_transactions.stock_transaction import StockTransaction
    from suppliers.supplier import Supplier

    payment_status_filter = request.args.get('payment_status')
    purchases = StockTransaction.query.filter_by(transaction_type='Purchase').all()
    result = []

    for p in purchases:
        supplier = Supplier.query.get(p.supplier_id) if p.supplier_id else None

        payment_status = "Pending"
        payment_method = None
        transaction_reference = None
        paid_amount = Decimal('0')
        total_amount = Decimal('0')

        if p.notes and p.notes.startswith('{'):
            try:
                notes_data = json.loads(p.notes)
                payment_status = notes_data.get('payment_status', 'Pending')
                payment_method = notes_data.get('payment_method')
                transaction_reference = notes_data.get('transaction_reference')
                paid_amount = Decimal(notes_data.get('payment_amount', '0'))
                total_amount = Decimal(notes_data.get('total_amount', '0'))
            except:
                payment_status = "Pending"

        # Fallback calculation if no stored total amount
        if total_amount == 0:
            total_amount = Decimal(str(p.product.purchase_price)) * Decimal(str(p.quantity)) if p.product else Decimal(
                '0')

        balance_amount = max(Decimal('0'), total_amount - paid_amount)

        # Update payment status based on actual balance
        if balance_amount == 0:
            payment_status = "Paid"
        elif paid_amount > 0:
            payment_status = "Partially Paid"
        else:
            payment_status = "Pending"

        # Apply payment status filter if provided
        if payment_status_filter and payment_status.lower() != payment_status_filter.lower():
            continue

        result.append({
            "purchase_id": p.id,
            "reference_number": p.reference_number,
            "supplier_id": p.supplier_id,
            "supplier_name": supplier.name if supplier else None,
            "product_id": p.product_id,
            "product_name": p.product.product_name if p.product else None,
            "quantity": p.quantity,
            "transaction_date": p.transaction_date.isoformat(),
            "total_amount": f"{total_amount:.2f}",
            "paid_amount": f"{paid_amount:.2f}",
            "balance_amount": f"{balance_amount:.2f}",
            "payment_status": payment_status,
            "payment_method": payment_method,
            "transaction_reference": transaction_reference
        })

    return jsonify(result), 200


@bp.route("/supplier/<int:supplier_id>", methods=["GET"])
@require_permission_jwt('purchases', 'read')
def get_purchases_by_supplier(supplier_id):
    from stock_transactions.stock_transaction import StockTransaction
    from suppliers.supplier import Supplier

    payment_status_filter = request.args.get('payment_status')

    purchases = StockTransaction.query.filter_by(transaction_type='Purchase', supplier_id=supplier_id).all()
    supplier = Supplier.query.get(supplier_id)

    if not supplier:
        return jsonify({"error": "Supplier not found"}), 404

    result = []
    for p in purchases:
        payment_status = "Pending"
        payment_method = None
        transaction_reference = None
        paid_amount = Decimal('0')
        total_amount = Decimal('0')

        if p.notes and p.notes.startswith('{'):
            try:
                notes_data = json.loads(p.notes)
                payment_status = notes_data.get('payment_status', 'Pending')
                payment_method = notes_data.get('payment_method')
                transaction_reference = notes_data.get('transaction_reference')
                paid_amount = Decimal(notes_data.get('payment_amount', '0'))
                total_amount = Decimal(notes_data.get('total_amount', '0'))
            except:
                payment_status = "Pending"

        if total_amount == 0:
            total_amount = Decimal(str(p.product.purchase_price)) * Decimal(str(p.quantity)) if p.product else Decimal(
                '0')

        balance_amount = max(Decimal('0'), total_amount - paid_amount)

        if balance_amount == 0:
            payment_status = "Paid"
        elif paid_amount > 0:
            payment_status = "Partially Paid"
        else:
            payment_status = "Pending"

        # Apply payment status filter if provided
        if payment_status_filter and payment_status.lower() != payment_status_filter.lower():
            continue

        result.append({
            "purchase_id": p.id,
            "reference_number": p.reference_number,
            "product_id": p.product_id,
            "product_name": p.product.product_name if p.product else None,
            "quantity": p.quantity,
            "transaction_date": p.transaction_date.isoformat(),
            "total_amount": f"{total_amount:.2f}",
            "paid_amount": f"{paid_amount:.2f}",
            "balance_amount": f"{balance_amount:.2f}",
            "payment_status": payment_status,
            "payment_method": payment_method,
            "transaction_reference": transaction_reference
        })

    return jsonify({
        "supplier": {
            "id": supplier.id,
            "name": supplier.name,
            "contact_person": supplier.contact_person,
            "phone": supplier.phone
        },
        "purchases": result
    }), 200


@bp.route("/<int:purchase_id>", methods=["GET"])
@require_permission_jwt('purchases', 'read')
def get_purchase_details(purchase_id):
    try:
        purchase_details = PurchaseService.get_purchase_details(purchase_id)
        if not purchase_details:
            return jsonify({"error": "Purchase not found"}), 404

        total_amt = Decimal(purchase_details["payment_details"]["grand_total"])
        paid_amt = Decimal(purchase_details["payment_details"]["payment_amount"])
        balance_amt = max(Decimal("0"), total_amt - paid_amt)

        if balance_amt <= 0:
            status = "Paid"
        elif paid_amt > 0:
            status = "Partially Paid"
        else:
            status = "Pending"

        products_dict = {}
        if purchase_details.get("products"):
            for product_item in purchase_details["products"]:
                sku = product_item["product_details"]["sku"]
                qty = product_item["purchase_details"]["quantity_purchased"]
                if sku in products_dict:
                    products_dict[sku]["quantity"] += qty
                else:
                    products_dict[sku] = {
                        "product_id": product_item["product_details"]["product_id"],
                        "name": product_item["product_details"]["name"],
                        "sku": sku,
                        "quantity": qty,
                        "unit_price": product_item["product_details"]["purchase_price"]
                    }
        else:
            sku = purchase_details["product_details"]["sku"]
            products_dict[sku] = {
                "product_id": purchase_details["product_details"]["product_id"],
                "name": purchase_details["product_details"]["name"],
                "sku": sku,
                "quantity": purchase_details["purchase_details"]["quantity_purchased"],
                "unit_price": purchase_details["product_details"]["purchase_price"]
            }

        products_list = list(products_dict.values())

        clean_response = {
            "purchase_id": purchase_details["purchase_id"],
            "reference_number": purchase_details["reference_number"],
            "purchase_date": purchase_details["purchase_details"]["purchase_date"],
            "supplier": {
                "id": purchase_details["supplier_details"]["id"],
                "name": purchase_details["supplier_details"]["name"],
                "contact_person": purchase_details["supplier_details"]["contact_person"],
                "phone": purchase_details["supplier_details"]["phone"],
                "email": purchase_details["supplier_details"].get("email"),
                "address": purchase_details["supplier_details"].get("address"),
                "gst_number": purchase_details["supplier_details"].get("gst_number")
            } if purchase_details.get("supplier_details") else None,
            "products": products_list,
            "payment": {
                "total_amount": str(total_amt),
                "paid_amount": str(paid_amt),
                "balance_due": str(balance_amt),
                "status": status
            }
        }

        return jsonify(clean_response), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 400

@bp.route("/adjustment/", methods=["GET"])
@require_permission_jwt('purchases', 'read')
def get_all_adjustment_details():
    """Get all adjustment details with new product, old product, and supplier information"""
    from stock_transactions.stock_transaction import StockTransaction
    from suppliers.supplier import Supplier
    from products.product import Product

    adjustments = StockTransaction.query.filter_by(transaction_type='Adjustment').all()
    result = []

    for adjustment in adjustments:
        supplier = Supplier.query.get(adjustment.supplier_id) if adjustment.supplier_id else None
        product = Product.query.get(adjustment.product_id) if adjustment.product_id else None

        # Parse notes for old product details
        old_product_details = None
        new_product_details = None
        
        if adjustment.notes and adjustment.notes.startswith('{'):
            try:
                notes_data = json.loads(adjustment.notes)
                if notes_data.get('exchange_type') == 'product_exchange':
                    old_product_data = notes_data.get('old_product', {})
                    new_product_data = notes_data.get('new_product', {})
                    
                    old_product_full = Product.query.get(old_product_data.get('product_id')) if old_product_data.get('product_id') else None
                    new_product_full = Product.query.get(new_product_data.get('product_id')) if new_product_data.get('product_id') else None
                    
                    old_product_details = {
                        "product_id": old_product_data.get('product_id'),
                        "product_name": old_product_data.get('product_name'),
                        "sku": old_product_full.sku if old_product_full else None,
                        "description": old_product_full.description if old_product_full else None,
                        "purchase_price": old_product_data.get('purchase_price'),
                        "quantity": old_product_data.get('quantity')
                    }
                    
                    new_product_details = {
                        "product_id": new_product_data.get('product_id'),
                        "product_name": new_product_data.get('product_name'),
                        "sku": new_product_full.sku if new_product_full else None,
                        "description": new_product_full.description if new_product_full else None,
                        "purchase_price": new_product_data.get('purchase_price'),
                        "quantity": new_product_data.get('quantity')
                    }
            except:
                pass
        
        # If no exchange data, use current product as new product
        if not new_product_details and product:
            new_product_details = {
                "product_id": product.id,
                "product_name": product.product_name,
                "sku": product.sku,
                "description": product.description,
                "purchase_price": str(product.purchase_price),
                "quantity": adjustment.quantity
            }
        
        result.append({
            "adjustment_id": adjustment.id,
            "reference_number": adjustment.reference_number,
            "transaction_date": adjustment.transaction_date.isoformat(),
            "old_product": old_product_details,
            "new_product": new_product_details,
            "supplier_details": {
                "id": supplier.id,
                "name": supplier.name,
                "contact_person": supplier.contact_person,
                "email": supplier.email,
                "phone": supplier.phone,
                "address": supplier.address,
                "gst_number": supplier.gst_number
            } if supplier else None,
            "notes": adjustment.notes
        })

    return jsonify(result), 200


@bp.route("/adjustment/list", methods=["GET"])
@require_permission_jwt('purchases', 'read')
def list_adjustments():
    from stock_transactions.stock_transaction import StockTransaction
    from suppliers.supplier import Supplier
    from products.product import Product

    adjustments = StockTransaction.query.filter_by(transaction_type='Adjustment').all()
    result = []

    for adj in adjustments:
        supplier = Supplier.query.get(adj.supplier_id) if adj.supplier_id else None
        product = Product.query.get(adj.product_id) if adj.product_id else None

        # Check if this is a product exchange (JSON notes)
        if adj.notes and adj.notes.startswith('{'):
            try:
                notes_data = json.loads(adj.notes)
                if notes_data.get('exchange_type') == 'product_exchange':
                    # Product exchange adjustment
                    difference_amount = Decimal(notes_data.get('difference_amount', '0'))
                    exchange_direction = notes_data.get('exchange_direction', 'no_payment')
                    
                    result.append({
                        "adjustment_id": adj.id,
                        "reference_number": adj.reference_number,
                        "supplier_id": adj.supplier_id,
                        "supplier_name": supplier.name if supplier else None,
                        "product_id": adj.product_id,
                        "product_name": product.product_name if product else None,
                        "quantity": adj.quantity,
                        "amount": f"{difference_amount:.2f}",
                        "supplier_pays_us": f"{difference_amount:.2f}" if exchange_direction == "receivable_from_supplier" else "0.00",
                        "we_pay_supplier": f"{difference_amount:.2f}" if exchange_direction == "payable_to_supplier" else "0.00",
                        "transaction_date": adj.transaction_date.isoformat(),
                        "notes": adj.notes
                    })
                    continue
            except:
                pass
        
        # Regular adjustment (non-exchange)
        amount = Decimal(str(product.purchase_price)) * abs(adj.quantity) if product else Decimal('0')
        result.append({
            "adjustment_id": adj.id,
            "reference_number": adj.reference_number,
            "supplier_id": adj.supplier_id,
            "supplier_name": supplier.name if supplier else None,
            "product_id": adj.product_id,
            "product_name": product.product_name if product else None,
            "quantity": adj.quantity,
            "amount": f"{amount:.2f}",
            "supplier_pays_us": f"{amount:.2f}" if adj.quantity > 0 else "0.00",
            "we_pay_supplier": f"{amount:.2f}" if adj.quantity < 0 else "0.00",
            "transaction_date": adj.transaction_date.isoformat(),
            "notes": adj.notes
        })

    return jsonify(result), 200


@bp.route("/adjustment/<int:adjustment_id>", methods=["GET"])
@require_permission_jwt('purchases', 'read')
def get_adjustment_details(adjustment_id):
    from stock_transactions.stock_transaction import StockTransaction
    from suppliers.supplier import Supplier
    from products.product import Product

    adjustment = StockTransaction.query.filter_by(id=adjustment_id, transaction_type='Adjustment').first()
    if not adjustment:
        return jsonify({"error": "Adjustment not found"}), 404

    supplier = Supplier.query.get(adjustment.supplier_id) if adjustment.supplier_id else None
    product = Product.query.get(adjustment.product_id) if adjustment.product_id else None

    # Check if this is a product exchange (JSON notes)
    if adjustment.notes and adjustment.notes.startswith('{'):
        try:
            notes_data = json.loads(adjustment.notes)
            if notes_data.get('exchange_type') == 'product_exchange':
                # Product exchange adjustment with full details
                old_product_data = notes_data.get('old_product', {})
                new_product_data = notes_data.get('new_product', {})
                difference_amount = Decimal(notes_data.get('difference_amount', '0'))
                exchange_direction = notes_data.get('exchange_direction', 'no_payment')
                
                # Get full product details for old and new products
                old_product_full = Product.query.get(old_product_data.get('product_id')) if old_product_data.get('product_id') else None
                new_product_full = Product.query.get(new_product_data.get('product_id')) if new_product_data.get('product_id') else None
                
                return jsonify({
                    "adjustment_id": adjustment.id,
                    "reference_number": adjustment.reference_number,
                    "exchange_type": "product_exchange",
                    "supplier_details": {
                        "id": supplier.id,
                        "name": supplier.name,
                        "contact_person": supplier.contact_person,
                        "email": supplier.email,
                        "phone": supplier.phone,
                        "alternate_phone": supplier.alternate_phone,
                        "address": supplier.address,
                        "gst_number": supplier.gst_number,
                        "payment_terms": supplier.payment_terms,
                        "bank_details": supplier.bank_details,
                        "notes": supplier.notes
                    } if supplier else None,
                    "old_product": {
                        "product_id": old_product_data.get('product_id'),
                        "product_name": old_product_data.get('product_name'),
                        "sku": old_product_full.sku if old_product_full else None,
                        "description": old_product_full.description if old_product_full else None,
                        "unit_of_measure": old_product_full.unit_of_measure if old_product_full else None,
                        "category_id": old_product_full.category_id if old_product_full else None,
                        "barcode": old_product_full.barcode if old_product_full else None,
                        "batch_number": old_product_full.batch_number if old_product_full else None,
                        "expiry_date": old_product_full.expiry_date.isoformat() if old_product_full and old_product_full.expiry_date else None,
                        "quantity": old_product_data.get('quantity'),
                        "purchase_price": old_product_data.get('purchase_price'),
                        "selling_price": str(old_product_full.selling_price) if old_product_full else None,
                        "current_stock": old_product_full.quantity_in_stock if old_product_full else None,
                        "total_amount": notes_data.get('old_total')
                    },
                    "new_product": {
                        "product_id": new_product_data.get('product_id'),
                        "product_name": new_product_data.get('product_name'),
                        "sku": new_product_full.sku if new_product_full else None,
                        "description": new_product_full.description if new_product_full else None,
                        "unit_of_measure": new_product_full.unit_of_measure if new_product_full else None,
                        "category_id": new_product_full.category_id if new_product_full else None,
                        "barcode": new_product_full.barcode if new_product_full else None,
                        "batch_number": new_product_full.batch_number if new_product_full else None,
                        "expiry_date": new_product_full.expiry_date.isoformat() if new_product_full and new_product_full.expiry_date else None,
                        "quantity": new_product_data.get('quantity'),
                        "purchase_price": new_product_data.get('purchase_price'),
                        "selling_price": str(new_product_full.selling_price) if new_product_full else None,
                        "current_stock": new_product_full.quantity_in_stock if new_product_full else None,
                        "total_amount": notes_data.get('new_total')
                    },
                    "financial_summary": {
                        "difference_amount": f"{difference_amount:.2f}",
                        "exchange_direction": exchange_direction,
                        "supplier_pays_us": f"{difference_amount:.2f}" if exchange_direction == "receivable_from_supplier" else "0.00",
                        "we_pay_supplier": f"{difference_amount:.2f}" if exchange_direction == "payable_to_supplier" else "0.00",
                        "balance_status": "Supplier owes us" if exchange_direction == "receivable_from_supplier" else "We owe supplier" if exchange_direction == "payable_to_supplier" else "No balance"
                    },
                    "transaction_date": adjustment.transaction_date.isoformat(),
                    "notes": adjustment.notes
                }), 200
        except:
            pass
    
    # Regular adjustment (non-exchange) with full details
    amount = Decimal(str(product.purchase_price)) * abs(adjustment.quantity) if product else Decimal('0')
    return jsonify({
        "adjustment_id": adjustment.id,
        "reference_number": adjustment.reference_number,
        "supplier_details": {
            "id": supplier.id,
            "name": supplier.name,
            "contact_person": supplier.contact_person,
            "email": supplier.email,
            "phone": supplier.phone,
            "alternate_phone": supplier.alternate_phone,
            "address": supplier.address,
            "gst_number": supplier.gst_number,
            "payment_terms": supplier.payment_terms,
            "bank_details": supplier.bank_details,
            "notes": supplier.notes
        } if supplier else None,
        "product": {
            "id": product.id,
            "product_name": product.product_name,
            "sku": product.sku,
            "description": product.description,
            "unit_of_measure": product.unit_of_measure,
            "category_id": product.category_id,
            "barcode": product.barcode,
            "batch_number": product.batch_number,
            "expiry_date": product.expiry_date.isoformat() if product.expiry_date else None,
            "purchase_price": str(product.purchase_price),
            "selling_price": str(product.selling_price),
            "current_stock": product.quantity_in_stock,
            "reorder_level": product.reorder_level,
            "max_stock_level": product.max_stock_level
        } if product else None,
        "quantity": adjustment.quantity,
        "amount": f"{amount:.2f}",
        "supplier_pays_us": f"{amount:.2f}" if adjustment.quantity > 0 else "0.00",
        "we_pay_supplier": f"{amount:.2f}" if adjustment.quantity < 0 else "0.00",
        "transaction_date": adjustment.transaction_date.isoformat(),
        "notes": adjustment.notes
    }), 200


@bp.route("/adjustment", methods=["POST"])
@require_permission_jwt('purchases', 'write')
@audit_decorator('purchases', 'ADJUSTMENT')
def process_purchase_adjustment():
    data = request.get_json() or {}
    required = ["supplier_id", "old_product", "new_product"]
    if not all(field in data for field in required):
        return jsonify({"error": f"Required fields: {required}"}), 400

    from src.extensions import db
    from stock_transactions.stock_transaction import StockTransaction
    from products.product import Product
    import json

    old_product = data["old_product"]
    new_product = data["new_product"]

    # Get product details and calculate prices
    old_prod = Product.query.get(old_product["product_id"])
    new_prod = Product.query.get(new_product["product_id"])
    
    if not old_prod:
        return jsonify({"error": "Old product not found"}), 400
    if not new_prod:
        return jsonify({"error": "New product not found"}), 400

    # Calculate amounts using actual purchase prices from database
    old_purchase_price = old_prod.purchase_price
    new_purchase_price = new_prod.purchase_price
    old_quantity = int(old_product["quantity"])
    new_quantity = int(new_product["quantity"])
    
    old_total = old_purchase_price * old_quantity
    new_total = new_purchase_price * new_quantity
    difference = new_total - old_total

    try:
        # Update stock for old product (add back)
        old_prod.quantity_in_stock += old_quantity
        # Update stock for new product (remove)
        new_prod.quantity_in_stock -= new_quantity

        # Create adjustment transaction with calculated amounts
        adjustment_notes = json.dumps({
            "exchange_type": "product_exchange",
            "old_product": {
                "product_id": old_product["product_id"],
                "product_name": old_product["product_name"],
                "quantity": old_quantity,
                "purchase_price": str(old_purchase_price)
            },
            "new_product": {
                "product_id": new_product["product_id"],
                "product_name": new_product["product_name"],
                "quantity": new_quantity,
                "purchase_price": str(new_purchase_price)
            },
            "old_total": str(old_total),
            "new_total": str(new_total),
            "difference_amount": str(abs(difference)),
            "exchange_direction": "payable_to_supplier" if difference > 0 else "receivable_from_supplier" if difference < 0 else "no_payment"
        })

        adjustment_transaction = StockTransaction(
            product_id=new_product["product_id"],
            transaction_type="Adjustment",
            quantity=0,
            supplier_id=data["supplier_id"],
            reference_number=f"EXC-{data.get('exchange_id', 1)}",
            notes=adjustment_notes
        )

        db.session.add(adjustment_transaction)
        db.session.commit()

        result = {
            "adjustment_id": adjustment_transaction.id,
            "exchange_id": data.get("exchange_id", 1),
            "supplier_id": data["supplier_id"],
            "old_product": {
                "product_id": old_product["product_id"],
                "product_name": old_product["product_name"],
                "quantity": old_quantity,
                "purchase_price": str(old_purchase_price),
                "total_amount": str(old_total)
            },
            "new_product": {
                "product_id": new_product["product_id"],
                "product_name": new_product["product_name"],
                "quantity": new_quantity,
                "purchase_price": str(new_purchase_price),
                "total_amount": str(new_total)
            },
            "difference_amount": str(abs(difference))
        }

        if difference > 0:
            result["payment_direction"] = "We need to pay supplier"
            result["we_pay_supplier"] = str(difference)
            result["supplier_pays_us"] = "0.00"
        elif difference < 0:
            result["payment_direction"] = "Supplier needs to pay us"
            result["supplier_pays_us"] = str(abs(difference))
            result["we_pay_supplier"] = "0.00"
        else:
            result["payment_direction"] = "No payment needed"
            result["we_pay_supplier"] = "0.00"
            result["supplier_pays_us"] = "0.00"

        return jsonify(result), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/<int:purchase_id>/purchase.html", methods=["GET"])
@require_permission_jwt('purchases', 'read')
def serve_purchase_invoice_html(purchase_id):
    import os
    try:
        template_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates', 'purchase_invoice.html')
        with open(template_path, 'r') as file:
            html_content = file.read()
        return html_content
    except Exception as e:
        return f"Error loading invoice template: {str(e)}", 400

@bp.route("/<int:purchase_id>/invoice", methods=["GET"])
@require_permission_jwt('purchases', 'read')
def generate_purchase_invoice(purchase_id):
    try:
        data = PurchaseService.get_purchase_details(purchase_id)
        if not data:
            return f"Purchase ID {purchase_id} not found", 404

        total_amt = Decimal(data["payment_details"]["grand_total"])
        paid_amt = Decimal(data["payment_details"]["payment_amount"])
        balance_amt = max(Decimal("0"), total_amt - paid_amt)

        if balance_amt <= 0:
            status = "Paid"
        elif paid_amt > 0:
            status = "Partially Paid"
        else:
            status = "Pending"

        data["payment_details"]["grand_total"] = str(total_amt)
        data["payment_details"]["balance_amount"] = str(balance_amt)
        data["payment_details"]["payment_status"] = status

        our_company = {
            "name": "Elephant Enterprises Pvt Ltd",
            "address": "45 Commerce Plaza, MG Road, Bangalore - 560001, Karnataka, India",
            "phone": "+91 98765 43210",
            "email": "info@elephantenterprises.com",
            "gst": "29AABCE2971B1Z5"
        }

        import os
        template_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates')
        env = Environment(loader=FileSystemLoader(template_dir))
        template = env.get_template('purchase_invoice.html')
        html_content = template.render(
            data=data,
            our_company=our_company,
            purchase_id=purchase_id
        )

        return html_content

    except Exception as e:
        return f"Error generating invoice: {str(e)}", 400


@bp.route("/export", methods=["GET"])
@require_permission_jwt('purchases', 'read')
def export_purchase_bills():
    try:
        format_type = request.args.get('format', 'csv').lower()
        
        from stock_transactions.stock_transaction import StockTransaction
        from suppliers.supplier import Supplier
        
        purchases = StockTransaction.query.filter_by(transaction_type='Purchase').all()
        data = []
        
        for p in purchases:
            supplier = Supplier.query.get(p.supplier_id) if p.supplier_id else None
            
            payment_status = "Pending"
            payment_method = None
            transaction_reference = None
            paid_amount = Decimal('0')
            total_amount = Decimal('0')
            
            if p.notes and p.notes.startswith('{'):
                try:
                    notes_data = json.loads(p.notes)
                    payment_status = notes_data.get('payment_status', 'Pending')
                    payment_method = notes_data.get('payment_method')
                    transaction_reference = notes_data.get('transaction_reference')
                    paid_amount = Decimal(notes_data.get('payment_amount', '0'))
                    total_amount = Decimal(notes_data.get('total_amount', '0'))
                except:
                    payment_status = "Pending"
            
            if total_amount == 0:
                total_amount = Decimal(str(p.product.purchase_price)) * Decimal(str(p.quantity)) if p.product else Decimal('0')
            
            balance_amount = max(Decimal('0'), total_amount - paid_amount)
            
            if balance_amount == 0:
                payment_status = "Paid"
            elif paid_amount > 0:
                payment_status = "Partially Paid"
            else:
                payment_status = "Pending"
            
            data.append({
                "Purchase ID": p.id,
                "Reference Number": p.reference_number,
                "Supplier ID": p.supplier_id or '',
                "Supplier Name": supplier.name if supplier else '',
                "Supplier Contact": supplier.contact_person if supplier else '',
                "Supplier Phone": supplier.phone if supplier else '',
                "Product ID": p.product_id,
                "Product Name": p.product.product_name if p.product else '',
                "Quantity": p.quantity,
                "Transaction Date": p.transaction_date.strftime('%Y-%m-%d %H:%M:%S'),
                "Total Amount": float(total_amount),
                "Paid Amount": float(paid_amount),
                "Balance Amount": float(balance_amount),
                "Payment Status": payment_status,
                "Payment Method": payment_method or '',
                "Transaction Reference": transaction_reference or ''
            })
        
        df = pd.DataFrame(data)
        
        if format_type == 'excel':
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Purchase Bills', index=False)
            output.seek(0)
            
            return send_file(
                output,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name=f'purchase_bills_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
            )
        else:
            output = io.StringIO()
            df.to_csv(output, index=False)
            response = make_response(output.getvalue())
            response.headers['Content-Type'] = 'text/csv; charset=utf-8'
            response.headers['Content-Disposition'] = f'attachment; filename=purchase_bills_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
            return response
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route("/export-all", methods=["GET"])
@require_permission_jwt('purchases', 'read')
def export_purchase_billing_all():
    try:
        format_type = request.args.get('format', 'csv').lower()
        export_type = request.args.get('type', 'all')  # all, adjustments, returns, damage
        
        from stock_transactions.stock_transaction import StockTransaction
        from suppliers.supplier import Supplier
        from returns.product_return import DamagedProduct
        from products.product import Product
        
        data = []
        
        if export_type in ['all', 'adjustments']:
            # Get adjustments
            adjustments = StockTransaction.query.filter_by(transaction_type='Adjustment').all()
            for adj in adjustments:
                supplier = Supplier.query.get(adj.supplier_id) if adj.supplier_id else None
                product = Product.query.get(adj.product_id) if adj.product_id else None
                
                if adj.notes and adj.notes.startswith('{'):
                    try:
                        notes_data = json.loads(adj.notes)
                        if notes_data.get('exchange_type') == 'product_exchange':
                            difference_amount = Decimal(notes_data.get('difference_amount', '0'))
                            exchange_direction = notes_data.get('exchange_direction', 'no_payment')
                            
                            data.append({
                                "Type": "Adjustment",
                                "ID": adj.id,
                                "Reference Number": adj.reference_number,
                                "Supplier ID": adj.supplier_id or '',
                                "Supplier Name": supplier.name if supplier else '',
                                "Product ID": adj.product_id,
                                "Product Name": product.product_name if product else '',
                                "Quantity": adj.quantity,
                                "Amount": float(difference_amount),
                                "Supplier Pays Us": float(difference_amount) if exchange_direction == "receivable_from_supplier" else 0,
                                "We Pay Supplier": float(difference_amount) if exchange_direction == "payable_to_supplier" else 0,
                                "Date": adj.transaction_date.strftime('%Y-%m-%d %H:%M:%S'),
                                "Notes": adj.notes or '',
                                "Status": '',
                            })
                            continue
                    except:
                        pass
                
                # Regular adjustment
                amount = Decimal(str(product.purchase_price)) * abs(adj.quantity) if product else Decimal('0')
                data.append({
                    "Type": "Adjustment",
                    "ID": adj.id,
                    "Reference Number": adj.reference_number,
                    "Supplier ID": adj.supplier_id or '',
                    "Supplier Name": supplier.name if supplier else '',
                    "Product ID": adj.product_id,
                    "Product Name": product.product_name if product else '',
                    "Quantity": adj.quantity,
                    "Amount": float(amount),
                    "Supplier Pays Us": float(amount) if adj.quantity > 0 else 0,
                    "We Pay Supplier": float(amount) if adj.quantity < 0 else 0,
                    "Date": adj.transaction_date.strftime('%Y-%m-%d %H:%M:%S'),
                    "Notes": adj.notes or '',
                    "Status": ''
                })
        
        if export_type in ['all', 'returns']:
            # Get returns
            returns = StockTransaction.query.filter_by(transaction_type='Return').all()
            for ret in returns:
                supplier = Supplier.query.get(ret.supplier_id) if ret.supplier_id else None
                product = Product.query.get(ret.product_id) if ret.product_id else None
                
                data.append({
                    "Type": "Return",
                    "ID": ret.id,
                    "Reference Number": ret.reference_number,
                    "Supplier ID": ret.supplier_id or '',
                    "Supplier Name": supplier.name if supplier else '',
                    "Product ID": ret.product_id,
                    "Product Name": product.product_name if product else '',
                    "Quantity": ret.quantity,
                    "Amount": float(product.purchase_price * ret.quantity) if product else 0,
                    "Supplier Pays Us": float(product.purchase_price * ret.quantity) if product else 0,
                    "We Pay Supplier": 0,
                    "Date": ret.transaction_date.strftime('%Y-%m-%d %H:%M:%S'),
                    "Notes": ret.notes or '',
                    "Status": '',
                    "Action Taken": '',
                    "Damage Reason": '',
                    "Repair Cost": ''
                })
        
        if export_type in ['all', 'damage']:
            # Get damage records
            damages = DamagedProduct.query.all()
            for damage in damages:
                product = Product.query.get(damage.product_id) if damage.product_id else None
                
                data.append({
                    "Type": "Damage",
                    "ID": damage.id,
                    "Reference Number": '',
                    "Supplier ID": '',
                    "Supplier Name": '',
                    "Product ID": damage.product_id,
                    "Product Name": product.product_name if product else '',
                    "Quantity": damage.quantity,
                    "Amount": float(damage.repair_cost or 0),
                    "Supplier Pays Us": 0,
                    "We Pay Supplier": float(damage.repair_cost or 0),
                    "Date": damage.damage_date.strftime('%Y-%m-%d %H:%M:%S'),
                    "Notes": '',
                    "Status": damage.status,
                    "Action Taken": damage.action_taken or '',
                    "Damage Reason": damage.damage_reason or '',
                    "Repair Cost": float(damage.repair_cost or 0)
                })
        
        df = pd.DataFrame(data)
        
        if format_type == 'excel':
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Purchase Billing', index=False)
            output.seek(0)
            
            return send_file(
                output,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name=f'purchase_billing_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
            )
        else:
            output = io.StringIO()
            df.to_csv(output, index=False)
            response = make_response(output.getvalue())
            response.headers['Content-Type'] = 'text/csv; charset=utf-8'
            response.headers['Content-Disposition'] = f'attachment; filename=purchase_billing_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
            return response
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route("/return/<int:return_id>", methods=["GET"])
@require_permission_jwt('purchases', 'read')
def get_return_details(return_id):
    from stock_transactions.stock_transaction import StockTransaction
    from suppliers.supplier import Supplier
    from products.product import Product
    
    return_record = StockTransaction.query.filter_by(id=return_id, transaction_type='Return').first()
    if not return_record:
        return jsonify({"error": "Return record not found"}), 404
    
    supplier = Supplier.query.get(return_record.supplier_id) if return_record.supplier_id else None
    product = Product.query.get(return_record.product_id) if return_record.product_id else None
    
    # Get original purchase details
    original_purchase = StockTransaction.query.filter_by(
        product_id=return_record.product_id,
        supplier_id=return_record.supplier_id,
        transaction_type='Purchase'
    ).first()
    
    return_amount = abs(return_record.quantity) * product.purchase_price if product else 0
    
    return jsonify({
        "return_id": return_record.id,
        "reference_number": return_record.reference_number,
        "supplier": {
            "id": supplier.id,
            "name": supplier.name,
            "contact_person": supplier.contact_person,
            "phone": supplier.phone,
            "email": supplier.email
        } if supplier else None,
        "product": {
            "id": product.id,
            "name": product.product_name,
            "sku": product.sku,
            "purchase_price": str(product.purchase_price)
        } if product else None,
        "original_purchase": {
            "purchase_id": original_purchase.id,
            "reference_number": original_purchase.reference_number,
            "purchase_date": original_purchase.transaction_date.isoformat(),
            "quantity_purchased": original_purchase.quantity
        } if original_purchase else None,
        "quantity_returned": abs(return_record.quantity),
        "return_amount": str(return_amount),
        "supplier_owes_us": str(return_amount),
        "return_date": return_record.transaction_date.isoformat(),
        "notes": return_record.notes
    }), 200