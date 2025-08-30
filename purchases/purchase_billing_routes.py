from flask import Blueprint, request, jsonify, render_template
from purchases.purchase_billing_service import PurchaseBillingService
from purchases.purchase_service import PurchaseService
from purchases.purchase_bill import PurchaseBill
from decimal import Decimal
import json
from jinja2 import Environment, FileSystemLoader

bp = Blueprint("purchase_billing", __name__)


@bp.route("/pay-supplier", methods=["POST"])
def pay_supplier():
    payload = request.get_json() or {}
    supplier_id = payload.get("supplier_id")
    supplier_name = payload.get("supplier_name")
    phone = payload.get("phone")
    payment_amount = payload.get("payment_amount")
    payment_method = payload.get("payment_method")

    if not all([supplier_id, supplier_name, phone, payment_amount, payment_method]):
        return jsonify({"error": "supplier_id, supplier_name, phone, payment_amount, payment_method required"}), 400

    try:
        result = PurchaseBillingService.create_purchase_bill_with_payment(
            supplier_id=supplier_id,
            supplier_name=supplier_name,
            contact_person=payload.get("contact_person"),
            email=payload.get("email"),
            phone=phone,
            address=payload.get("address"),
            gst_number=payload.get("gst_number"),
            payment_amount=payment_amount,
            payment_method=payment_method,
            bank_details=payload.get("bank_details"),
            transaction_reference=payload.get("transaction_reference"),
            notes=payload.get("notes")
        )
        return jsonify(result), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400


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
            total_amount = Decimal(str(p.product.purchase_price)) * Decimal(str(p.quantity)) if p.product else Decimal('0')

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
            total_amount = Decimal(str(p.product.purchase_price)) * Decimal(str(p.quantity)) if p.product else Decimal('0')

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
                "phone": purchase_details["supplier_details"]["phone"]
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


@bp.route("/bill/<int:bill_id>", methods=["GET"])
def get_purchase_bill(bill_id):
    try:
        bill_details = PurchaseBillingService.get_purchase_bill_details(bill_id)
        if not bill_details:
            return jsonify({"error": "Purchase bill not found"}), 404
        return jsonify(bill_details), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/<int:bill_id>/status", methods=["PUT"])
def update_payment_status(bill_id):
    from extensions import db
    bill = PurchaseBill.query.get(bill_id)
    if not bill:
        return jsonify({"error": "Purchase bill not found"}), 404

    data = request.get_json() or {}
    bill.payment_status = data.get("payment_status", bill.payment_status)
    bill.transaction_reference = data.get("transaction_reference", bill.transaction_reference)
    db.session.commit()

    return jsonify({
        "id": bill.id,
        "payment_status": bill.payment_status,
        "transaction_reference": bill.transaction_reference
    }), 200


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


@bp.route("/adjustment", methods=["GET"])
def list_adjustments():
    from stock_transactions.stock_transaction import StockTransaction
    from suppliers.supplier import Supplier
    from products.product import Product
    
    adjustments = StockTransaction.query.filter_by(transaction_type='Adjustment').all()
    result = []
    
    for adj in adjustments:
        supplier = Supplier.query.get(adj.supplier_id) if adj.supplier_id else None
        product = Product.query.get(adj.product_id) if adj.product_id else None
        
        # Calculate payment amount from product price and quantity
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
    
    # Calculate payment amount from product price and quantity
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
        
        # Create return transaction
        return_transaction = StockTransaction(
            product_id=old_product["product_id"],
            transaction_type="Adjustment",
            quantity=old_product["quantity"],
            supplier_id=data["supplier_id"],
            reference_number=f"EXC-{data.get('exchange_id', 1)}",
            notes=f"Exchange Return - {old_product['product_name']}"
        )
        
        # Create exchange transaction
        exchange_transaction = StockTransaction(
            product_id=new_product["product_id"],
            transaction_type="Adjustment",
            quantity=-new_product["quantity"],
            supplier_id=data["supplier_id"],
            reference_number=f"EXC-{data.get('exchange_id', 1)}",
            notes=f"Exchange Send - {new_product['product_name']}"
        )
        
        db.session.add(return_transaction)
        db.session.add(exchange_transaction)
        db.session.commit()
        
        result = {
            "return_transaction_id": return_transaction.id,
            "exchange_transaction_id": exchange_transaction.id,
            "exchange_id": data.get("exchange_id", 1),
            "supplier_id": data["supplier_id"],
            "old_product": old_product,
            "new_product": new_product,
            "old_total": str(old_total),
            "new_total": str(new_total),
            "difference_amount": str(abs(difference))
        }
        
        if difference > 0:
            result["exchange_type"] = "receivable_from_supplier"
            result["supplier_pays_us"] = str(difference)
        elif difference < 0:
            result["exchange_type"] = "payable_to_supplier"
            result["we_pay_supplier"] = str(abs(difference))
        else:
            result["exchange_type"] = "no_payment"
            result["no_payment_needed"] = True
        
        return jsonify(result), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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

        env = Environment(loader=FileSystemLoader('.'))
        template = env.get_template('purchase_invoice.html')
        html_content = template.render(
            data=data,
            our_company=our_company,
            purchase_id=purchase_id
        )

        return html_content

    except Exception as e:
        return f"Error generating invoice: {str(e)}", 400
