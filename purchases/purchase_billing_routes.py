from flask import Blueprint, request, jsonify, render_template
from purchases.purchase_billing_service import PurchaseBillingService
from purchases.purchase_service import PurchaseService
from purchases.purchase_bill import PurchaseBill
from decimal import Decimal
import json
from jinja2 import Environment, FileSystemLoader

bp = Blueprint("purchase_billing", __name__)

@bp.route("/damage/", methods=["POST"])
def create_damage_record():
    from extensions import db
    from purchases.supplier_damage import SupplierDamage
    from products.product import Product
    
    data = request.get_json() or {}
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
        
        damage = SupplierDamage(
            purchase_id=data["purchase_id"],
            supplier_id=data["supplier_id"],
            product_id=data["product_id"],
            quantity_damaged=quantity_damaged,
            damage_type=damage_type,
            damage_reason=data.get("damage_reason"),
            unit_price=product.purchase_price,
            refund_amount=refund_amount,
            status="Paid" if damage_type == "refund" else "Replaced",
            supplier_response=supplier_response,
            replacement_quantity=replacement_quantity,
            replacement_date=replacement_date,
            notes=data.get("notes"),
            created_by=data.get("created_by")
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


@bp.route("/damage/", methods=["GET"])
def list_damage_records():
    from purchases.supplier_damage import SupplierDamage
    
    supplier_id = request.args.get('supplier_id')
    query = SupplierDamage.query
    if supplier_id:
        query = query.filter_by(supplier_id=supplier_id)
    
    damages = query.all()
    result = []
    
    for damage in damages:
        result.append({
            "damage_id": damage.id,
            "damage_number": damage.damage_number,
            "purchase_id": damage.purchase_id,
            "supplier_name": damage.supplier.name if damage.supplier else None,
            "product_name": damage.product.product_name if damage.product else None,
            "quantity_damaged": damage.quantity_damaged,
            "damage_type": damage.damage_type,
            "unit_price": str(damage.unit_price),
            "total_amount": str(damage.total_amount),
            "refund_amount": str(damage.refund_amount),
            "status": damage.status,
            "damage_date": damage.damage_date.isoformat()
        })
    
    return jsonify(result), 200


@bp.route("/damage/<int:damage_id>", methods=["GET"])
def get_damage_details(damage_id):
    from purchases.supplier_damage import SupplierDamage
    
    damage = SupplierDamage.query.get(damage_id)
    if not damage:
        return jsonify({"error": "Damage record not found"}), 404
    
    return jsonify({
        "damage_id": damage.id,
        "damage_number": damage.damage_number,
        "purchase_id": damage.purchase_id,
        "supplier": {
            "id": damage.supplier.id,
            "name": damage.supplier.name,
            "contact_person": damage.supplier.contact_person,
            "phone": damage.supplier.phone
        } if damage.supplier else None,
        "product": {
            "id": damage.product.id,
            "name": damage.product.product_name,
            "sku": damage.product.sku
        } if damage.product else None,
        "damage_details": {
            "quantity_damaged": damage.quantity_damaged,
            "damage_type": damage.damage_type,
            "damage_reason": damage.damage_reason,
            "damage_date": damage.damage_date.isoformat()
        },
        "financial_details": {
            "unit_price": str(damage.unit_price),
            "total_amount": str(damage.total_amount),
            "refund_amount": str(damage.refund_amount)
        },
        "status_tracking": {
            "status": damage.status,
            "supplier_response": damage.supplier_response,
            "created_by": damage.created_by,
            "resolved_by": damage.resolved_by,
            "resolved_date": damage.resolved_date.isoformat() if damage.resolved_date else None
        },
        "replacement_details": {
            "replacement_quantity": damage.replacement_quantity,
            "replacement_date": damage.replacement_date.isoformat() if damage.replacement_date else None
        },
        "notes": damage.notes,
        "created_at": damage.created_at.isoformat(),
        "updated_at": damage.updated_at.isoformat() if damage.updated_at else None
    }), 200


@bp.route("/", methods=["GET"])
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


@bp.route("/return", methods=["POST"])
def process_purchase_return():
    data = request.get_json() or {}
    required = ["purchase_id", "product_id", "quantity", "original_price"]
    if not all(field in data for field in required):
        return jsonify({"error": f"Required fields: {required}"}), 400

    from stock_transactions.transaction_service import TransactionService
    quantity = int(data["quantity"])
    original_price = Decimal(str(data["original_price"]))
    refund_amount = quantity * original_price

    transaction_data = {
        "transaction_type": "Return",
        "product_id": data["product_id"],
        "quantity": quantity,
        "original_price": str(original_price),
        "reference_number": f"RET-{data['purchase_id']}"
    }

    try:
        result = TransactionService.process_transaction(transaction_data)
        if "error" in result:
            return jsonify(result), 400

        result["supplier_owes"] = str(refund_amount)
        return jsonify(result), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/adjustment/", methods=["GET"])
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
                # Product exchange adjustment
                old_product_data = notes_data.get('old_product', {})
                new_product_data = notes_data.get('new_product', {})
                difference_amount = Decimal(notes_data.get('difference_amount', '0'))
                exchange_direction = notes_data.get('exchange_direction', 'no_payment')
                
                return jsonify({
                    "adjustment_id": adjustment.id,
                    "reference_number": adjustment.reference_number,
                    "exchange_type": "product_exchange",
                    "supplier": {
                        "id": supplier.id,
                        "name": supplier.name,
                        "contact_person": supplier.contact_person,
                        "phone": supplier.phone
                    } if supplier else None,
                    "old_product": {
                        "product_id": old_product_data.get('product_id'),
                        "product_name": old_product_data.get('product_name'),
                        "quantity": old_product_data.get('quantity'),
                        "purchase_price": old_product_data.get('purchase_price'),
                        "total_amount": notes_data.get('old_total')
                    },
                    "new_product": {
                        "product_id": new_product_data.get('product_id'),
                        "product_name": new_product_data.get('product_name'),
                        "quantity": new_product_data.get('quantity'),
                        "purchase_price": new_product_data.get('purchase_price'),
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
    
    # Regular adjustment (non-exchange)
    amount = Decimal(str(product.purchase_price)) * abs(adjustment.quantity) if product else Decimal('0')
    return jsonify({
        "adjustment_id": adjustment.id,
        "reference_number": adjustment.reference_number,
        "supplier": {
            "id": supplier.id,
            "name": supplier.name,
            "contact_person": supplier.contact_person,
            "phone": supplier.phone
        } if supplier else None,
        "product": {
            "id": product.id,
            "name": product.product_name,
            "sku": product.sku,
            "purchase_price": str(product.purchase_price)
        } if product else None,
        "quantity": adjustment.quantity,
        "amount": f"{amount:.2f}",
        "supplier_pays_us": f"{amount:.2f}" if adjustment.quantity > 0 else "0.00",
        "we_pay_supplier": f"{amount:.2f}" if adjustment.quantity < 0 else "0.00",
        "transaction_date": adjustment.transaction_date.isoformat(),
        "notes": adjustment.notes
    }), 200


@bp.route("/adjustment", methods=["POST"])
def process_purchase_adjustment():
    data = request.get_json() or {}
    required = ["supplier_id", "old_product", "new_product"]
    if not all(field in data for field in required):
        return jsonify({"error": f"Required fields: {required}"}), 400

    from extensions import db
    from stock_transactions.stock_transaction import StockTransaction
    from products.product import Product
    import json

    old_product = data["old_product"]
    new_product = data["new_product"]

    old_total = Decimal(str(old_product["purchase_price"])) * int(old_product["quantity"])
    new_total = Decimal(str(new_product["purchase_price"])) * int(new_product["quantity"])
    difference = new_total - old_total

    try:
        # Update stock for old product (add back)
        old_prod = Product.query.get(old_product["product_id"])
        if not old_prod:
            return jsonify({"error": "Old product not found"}), 400
        old_prod.quantity_in_stock += old_product["quantity"]

        # Update stock for new product (remove)
        new_prod = Product.query.get(new_product["product_id"])
        if not new_prod:
            return jsonify({"error": "New product not found"}), 400
        new_prod.quantity_in_stock -= new_product["quantity"]

        # Create single adjustment transaction with both products in notes
        adjustment_notes = json.dumps({
            "exchange_type": "product_exchange",
            "old_product": old_product,
            "new_product": new_product,
            "old_total": str(old_total),
            "new_total": str(new_total),
            "difference_amount": str(abs(difference)),
            "exchange_direction": "payable_to_supplier" if difference > 0 else "receivable_from_supplier" if difference < 0 else "no_payment"
        })

        adjustment_transaction = StockTransaction(
            product_id=new_product["product_id"],  # Use new product as primary
            transaction_type="Adjustment",
            quantity=0,  # Net quantity change (handled in stock updates above)
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
            "old_product": old_product,
            "new_product": new_product,
            "old_total": str(old_total),
            "new_total": str(new_total),
            "difference_amount": str(abs(difference))
        }

        if difference > 0:
            result["exchange_type"] = "payable_to_supplier"
            result["we_pay_supplier"] = str(difference)
        elif difference < 0:
            result["exchange_type"] = "receivable_from_supplier"
            result["supplier_pays_us"] = str(abs(difference))
        else:
            result["exchange_type"] = "no_payment"
            result["no_payment_needed"] = True

        return jsonify(result), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/<int:purchase_id>/purchase.html", methods=["GET"])
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