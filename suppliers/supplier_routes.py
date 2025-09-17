from flask import Blueprint, request, jsonify, make_response
from src.extensions import db
from suppliers.supplier import Supplier
from customers.customer import Customer
from stock_transactions.stock_transaction import StockTransaction
from user.enhanced_auth_middleware import require_permission_jwt
from user.audit_logger import audit_decorator
import csv
import io
from datetime import datetime

bp = Blueprint("suppliers", __name__)

@bp.route("/", methods=["POST"])
@require_permission_jwt('suppliers', 'write')
@audit_decorator('suppliers', 'CREATE')
def create_supplier():
    data = request.get_json() or {}
    
    # Handle array of suppliers
    if isinstance(data, list):
        created = []
        try:
            for item in data:
                if not item.get("phone"):
                    continue
                s = Supplier(
                    name=item.get("name"),
                    contact_person=item.get("contact_person"),
                    email=item.get("email"),
                    phone=item.get("phone"),
                    alternate_phone=item.get("alternate_phone"),
                    address=item.get("address"),
                    gst_number=item.get("gst_number"),
                    bank_details=item.get("bank_details"),
                    payment_terms=item.get("payment_terms"),
                    notes=item.get("notes"),
                )
                db.session.add(s)
                created.append({"id": s.id, "name": s.name, "phone": s.phone})
            db.session.commit()
            return jsonify({"created": len(created), "suppliers": created}), 201
        except Exception as e:
            db.session.rollback()
            return jsonify({"error": str(e)}), 400
    
    # Handle single supplier
    if not data.get("phone"):
        return jsonify({"error": "phone is required"}), 400
    try:
        s = Supplier(
            name=data.get("name"),
            contact_person=data.get("contact_person"),
            email=data.get("email"),
            phone=data.get("phone"),
            alternate_phone=data.get("alternate_phone"),
            address=data.get("address"),
            gst_number=data.get("gst_number"),
            bank_details=data.get("bank_details"),
            payment_terms=data.get("payment_terms"),
            notes=data.get("notes"),
        )
        db.session.add(s)
        db.session.commit()
        return jsonify({"id": s.id, "name": s.name, "phone": s.phone}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400

@bp.route("/", methods=["GET"])
@require_permission_jwt('suppliers', 'read')
def list_suppliers():
    search = request.args.get('search', '').strip()
    
    if search:
        sup = Supplier.query.filter(
            db.or_(
                Supplier.phone.ilike(f'%{search}%'),
                Supplier.contact_person.ilike(f'%{search}%'),
                Supplier.name.ilike(f'%{search}%')
            )
        ).all()
    else:
        sup = Supplier.query.all()
    
    return jsonify([{
        "id": x.id, 
        "name": x.name, 
        "contact_person": x.contact_person,
        "phone": x.phone,
        "alternate_phone": x.alternate_phone,
        "email": x.email,
        "address": x.address,
        "gst_number": x.gst_number,
        "payment_terms": x.payment_terms,
        "bank_details": x.bank_details,
        "notes": x.notes,
        "created_at": x.created_at.isoformat(),
        "updated_at": x.updated_at.isoformat() if x.updated_at else None
    } for x in sup]), 200

@bp.route("/<int:supplier_id>", methods=["GET"])
@require_permission_jwt('suppliers', 'read')
def get_supplier(supplier_id):
    s = Supplier.query.get(supplier_id)
    if not s:
        return jsonify({"error": "empty"}), 404
    
    purchases = StockTransaction.query.filter_by(supplier_id=supplier_id, transaction_type="Purchase").all()
    purchase_transactions = []
    
    for p in purchases:
        import json
        payment_info = {}
        if p.notes:
            try:
                payment_info = json.loads(p.notes)
            except:
                pass
        
        from decimal import Decimal
        total_amt = payment_info.get("total_amount", "0")
        payment_amt = payment_info.get("payment_amount", "0")
        
        # Get product details for this transaction
        from products.product import Product
        from category.category import Category
        
        product_details = []
        for product_info in payment_info.get("products", []):
            product = Product.query.get(product_info["product_id"])
            category = Category.query.get(product.category_id) if product and product.category_id else None
            
            product_details.append({
                "product_id": product_info["product_id"],
                "name": product_info["name"],
                "sku": product_info["sku"],
                "category_id": product.category_id if product else None,
                "category_name": category.name if category else None,
                "quantity_purchased": product_info["quantity_added"],
                "purchase_price": product_info["purchase_price"],
                "amount": product_info["amount"],
                "current_stock": product.quantity_in_stock if product else None,
                "reorder_level": product.reorder_level if product else None,
                "unit_of_measure": product.unit_of_measure if product else None,
                "barcode": product.barcode if product else None
            })
        
        balance_due = f"{max(Decimal('0'), Decimal(total_amt) - Decimal(payment_amt)):.2f}"
        
        purchase_transactions.append({
            "id": p.id,
            "reference_number": p.reference_number,
            "transaction_date": p.transaction_date.isoformat(),
            "total_quantity": p.quantity,
            "payment_details": {
                "total_amount": f"{Decimal(total_amt):.2f}",
                "payment_amount": f"{Decimal(payment_amt):.2f}",
                "balance_due": balance_due,
                "payment_method": payment_info.get("payment_method"),
                "payment_status": payment_info.get("payment_status", "Pending"),
                "transaction_reference": payment_info.get("transaction_reference")
            },
            "products": product_details,
            "purchase_summary": {
                "total_products": len(product_details),
                "total_quantity": sum(int(pd["quantity_purchased"]) for pd in product_details),
                "notes": p.notes
            }
        })
    
    return jsonify({
        "id": s.id, 
        "name": s.name, 
        "contact_person": s.contact_person, 
        "phone": s.phone, 
        "email": s.email, 
        "address": s.address, 
        "gst_number": s.gst_number, 
        "payment_terms": s.payment_terms,
        "bank_details": s.bank_details,
        "notes": s.notes,
        "created_at": s.created_at.isoformat(),
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        "purchase_transactions": purchase_transactions
    }), 200

@bp.route("/<int:supplier_id>/purchase-history", methods=["GET"])
@require_permission_jwt('suppliers', 'read')
def get_supplier_purchase_history(supplier_id):
    s = Supplier.query.get(supplier_id)
    if not s:
        return jsonify({"error": "Supplier not found"}), 404
    
    # Date and payment status filtering
    from datetime import datetime
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    payment_status = request.args.get('payment_status')
    
    query = StockTransaction.query.filter_by(supplier_id=supplier_id, transaction_type="Purchase")
    
    if date_from:
        try:
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(StockTransaction.transaction_date >= date_from_obj)
        except ValueError:
            return jsonify({"error": "Invalid date_from format. Use YYYY-MM-DD"}), 400
    
    if date_to:
        try:
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d')
            query = query.filter(StockTransaction.transaction_date <= date_to_obj)
        except ValueError:
            return jsonify({"error": "Invalid date_to format. Use YYYY-MM-DD"}), 400
    
    purchases = query.order_by(StockTransaction.transaction_date.desc()).all()
    
    # Filter by payment status if provided
    if payment_status:
        filtered_purchases = []
        for p in purchases:
            import json
            payment_info = {}
            if p.notes:
                try:
                    payment_info = json.loads(p.notes)
                except:
                    pass
            if payment_info.get("payment_status", "Pending").lower() == payment_status.lower():
                filtered_purchases.append(p)
        purchases = filtered_purchases
    purchase_history = []
    
    for p in purchases:
        import json
        payment_info = {}
        if p.notes:
            try:
                payment_info = json.loads(p.notes)
            except:
                pass
        
        from products.product import Product
        from category.category import Category
        from decimal import Decimal
        
        product_details = []
        for product_info in payment_info.get("products", []):
            product = Product.query.get(product_info["product_id"])
            category = Category.query.get(product.category_id) if product and product.category_id else None
            
            product_details.append({
                "product_id": product_info["product_id"],
                "name": product_info["name"],
                "sku": product_info["sku"],
                "category_id": product.category_id if product else None,
                "category_name": category.name if category else None,
                "quantity_purchased": product_info["quantity_added"],
                "purchase_price": product_info["purchase_price"],
                "amount": product_info["amount"],
                "current_stock": product.quantity_in_stock if product else None,
                "unit_of_measure": product.unit_of_measure if product else None
            })
        
        purchase_history.append({
            "purchase_id": p.id,
            "reference_number": p.reference_number,
            "purchase_date": p.transaction_date.isoformat(),
            "total_quantity": p.quantity,
            "products": product_details,
            "purchase_summary": {
                "total_products": len(product_details),
                "total_quantity": sum(int(pd["quantity_purchased"]) for pd in product_details)
            }
        })
    
    return jsonify({
        "supplier": {
            "id": s.id,
            "name": s.name,
            "contact_person": s.contact_person
        },
        "purchase_history": purchase_history
    }), 200


@bp.route("/<int:supplier_id>/payment-history", methods=["GET"])
@require_permission_jwt('suppliers', 'read')
def get_supplier_payment_history(supplier_id):
    s = Supplier.query.get(supplier_id)
    if not s:
        return jsonify({"error": "Supplier not found"}), 404
    
    # Date and payment status filtering
    from datetime import datetime
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    payment_status = request.args.get('payment_status')
    
    query = StockTransaction.query.filter_by(supplier_id=supplier_id, transaction_type="Purchase")
    
    if date_from:
        try:
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(StockTransaction.transaction_date >= date_from_obj)
        except ValueError:
            return jsonify({"error": "Invalid date_from format. Use YYYY-MM-DD"}), 400
    
    if date_to:
        try:
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d')
            query = query.filter(StockTransaction.transaction_date <= date_to_obj)
        except ValueError:
            return jsonify({"error": "Invalid date_to format. Use YYYY-MM-DD"}), 400
    
    purchases = query.order_by(StockTransaction.transaction_date.desc()).all()
    
    # Filter by payment status if provided
    if payment_status:
        filtered_purchases = []
        for p in purchases:
            import json
            payment_info = {}
            if p.notes:
                try:
                    payment_info = json.loads(p.notes)
                except:
                    pass
            if payment_info.get("payment_status", "Pending").lower() == payment_status.lower():
                filtered_purchases.append(p)
        purchases = filtered_purchases
    payment_history = []
    
    for p in purchases:
        import json
        payment_info = {}
        if p.notes:
            try:
                payment_info = json.loads(p.notes)
            except:
                pass
        
        from decimal import Decimal
        total_amt = payment_info.get("total_amount", "0")
        payment_amt = payment_info.get("payment_amount", "0")
        balance_due = f"{max(Decimal('0'), Decimal(total_amt) - Decimal(payment_amt)):.2f}"
        
        payment_history.append({
            "purchase_id": p.id,
            "reference_number": p.reference_number,
            "transaction_date": p.transaction_date.isoformat(),
            "total_amount": f"{Decimal(total_amt):.2f}",
            "payment_amount": f"{Decimal(payment_amt):.2f}",
            "balance_due": balance_due,
            "payment_method": payment_info.get("payment_method"),
            "payment_status": payment_info.get("payment_status", "Pending"),
            "transaction_reference": payment_info.get("transaction_reference")
        })
    
    return jsonify({
        "supplier": {
            "id": s.id,
            "name": s.name,
            "contact_person": s.contact_person
        },
        "payment_history": payment_history
    }), 200


@bp.route("/purchase-history", methods=["GET"])
@require_permission_jwt('suppliers', 'read')
def get_all_purchase_history():
    from datetime import datetime
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    payment_status = request.args.get('payment_status')
    
    query = StockTransaction.query.filter_by(transaction_type="Purchase")
    
    if date_from:
        try:
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(StockTransaction.transaction_date >= date_from_obj)
        except ValueError:
            return jsonify({"error": "Invalid date_from format. Use YYYY-MM-DD"}), 400
    
    if date_to:
        try:
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d')
            query = query.filter(StockTransaction.transaction_date <= date_to_obj)
        except ValueError:
            return jsonify({"error": "Invalid date_to format. Use YYYY-MM-DD"}), 400
    
    purchases = query.order_by(StockTransaction.transaction_date.desc()).all()
    
    # Filter by payment status if provided
    if payment_status:
        filtered_purchases = []
        for p in purchases:
            import json
            payment_info = {}
            if p.notes:
                try:
                    payment_info = json.loads(p.notes)
                except:
                    pass
            if payment_info.get("payment_status", "Pending").lower() == payment_status.lower():
                filtered_purchases.append(p)
        purchases = filtered_purchases
    
    purchase_history = []
    
    for p in purchases:
        supplier = Supplier.query.get(p.supplier_id)
        import json
        payment_info = {}
        if p.notes:
            try:
                payment_info = json.loads(p.notes)
            except:
                pass
        
        from products.product import Product
        from category.category import Category
        
        product_details = []
        for product_info in payment_info.get("products", []):
            product = Product.query.get(product_info["product_id"])
            category = Category.query.get(product.category_id) if product and product.category_id else None
            
            product_details.append({
                "product_id": product_info["product_id"],
                "name": product_info["name"],
                "sku": product_info["sku"],
                "category_id": product.category_id if product else None,
                "category_name": category.name if category else None,
                "quantity_purchased": product_info["quantity_added"],
                "purchase_price": product_info["purchase_price"],
                "amount": product_info["amount"]
            })
        
        purchase_history.append({
            "purchase_id": p.id,
            "reference_number": p.reference_number,
            "purchase_date": p.transaction_date.isoformat(),
            "supplier": {
                "id": supplier.id if supplier else None,
                "name": supplier.name if supplier else None,
                "contact_person": supplier.contact_person if supplier else None
            },
            "total_quantity": p.quantity,
            "products": product_details,
            "purchase_summary": {
                "total_products": len(product_details),
                "total_quantity": sum(int(pd["quantity_purchased"]) for pd in product_details)
            }
        })
    
    return jsonify({"purchase_history": purchase_history}), 200

@bp.route("/payment-history", methods=["GET"])
@require_permission_jwt('suppliers', 'read')
def get_all_payment_history():
    from datetime import datetime
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    payment_status = request.args.get('payment_status')
    
    query = StockTransaction.query.filter_by(transaction_type="Purchase")
    
    if date_from:
        try:
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(StockTransaction.transaction_date >= date_from_obj)
        except ValueError:
            return jsonify({"error": "Invalid date_from format. Use YYYY-MM-DD"}), 400
    
    if date_to:
        try:
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d')
            query = query.filter(StockTransaction.transaction_date <= date_to_obj)
        except ValueError:
            return jsonify({"error": "Invalid date_to format. Use YYYY-MM-DD"}), 400
    
    purchases = query.order_by(StockTransaction.transaction_date.desc()).all()
    
    # Filter by payment status if provided
    if payment_status:
        filtered_purchases = []
        for p in purchases:
            import json
            payment_info = {}
            if p.notes:
                try:
                    payment_info = json.loads(p.notes)
                except:
                    pass
            if payment_info.get("payment_status", "Pending").lower() == payment_status.lower():
                filtered_purchases.append(p)
        purchases = filtered_purchases
    
    payment_history = []
    
    for p in purchases:
        supplier = Supplier.query.get(p.supplier_id)
        import json
        payment_info = {}
        if p.notes:
            try:
                payment_info = json.loads(p.notes)
            except:
                pass
        
        from decimal import Decimal
        total_amt = payment_info.get("total_amount", "0")
        payment_amt = payment_info.get("payment_amount", payment_info.get("amount_paid", "0"))
        
        # If payment_amount is still 0, calculate from products
        if payment_amt == "0" and payment_info.get("products"):
            calculated_total = sum(float(prod.get("amount", 0)) for prod in payment_info.get("products", []))
            total_amt = str(calculated_total) if total_amt == "0" else total_amt
        
        balance_due = f"{max(Decimal('0'), Decimal(total_amt) - Decimal(payment_amt)):.2f}"
        
        payment_history.append({
            "purchase_id": p.id,
            "reference_number": p.reference_number,
            "transaction_date": p.transaction_date.isoformat(),
            "supplier": {
                "id": supplier.id if supplier else None,
                "name": supplier.name if supplier else None,
                "contact_person": supplier.contact_person if supplier else None
            },
            "total_amount": f"{Decimal(total_amt):.2f}",
            "payment_amount": f"{Decimal(payment_amt):.2f}",
            "balance_due": balance_due,
            "payment_method": payment_info.get("payment_method"),
            "payment_status": payment_info.get("payment_status", "Pending"),
            "transaction_reference": payment_info.get("transaction_reference")
        })
    
    return jsonify({"payment_history": payment_history}), 200

@bp.route("/export/csv", methods=["GET"])
@require_permission_jwt('suppliers', 'read')
def export_suppliers_csv():
    try:
        suppliers = Supplier.query.all()
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            'ID', 'Name', 'Contact Person', 'Phone', 'Alternate Phone', 
            'Email', 'Address', 'GST Number', 'Payment Terms', 
            'Bank Details', 'Notes', 'Created At', 'Updated At'
        ])
        
        # Write data
        for supplier in suppliers:
            writer.writerow([
                supplier.id,
                supplier.name or '',
                supplier.contact_person or '',
                supplier.phone or '',
                supplier.alternate_phone or '',
                supplier.email or '',
                supplier.address or '',
                supplier.gst_number or '',
                supplier.payment_terms or '',
                str(supplier.bank_details) if supplier.bank_details else '',
                supplier.notes or '',
                supplier.created_at.strftime('%Y-%m-%d %H:%M:%S') if supplier.created_at else '',
                supplier.updated_at.strftime('%Y-%m-%d %H:%M:%S') if supplier.updated_at else ''
            ])
        
        output.seek(0)
        response = make_response(output.getvalue())
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename=suppliers_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        
        return response
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route("/export/excel", methods=["GET"])
@require_permission_jwt('suppliers', 'read')
def export_suppliers_excel():
    try:
        import pandas as pd
        
        suppliers = Supplier.query.all()
        
        data = []
        for supplier in suppliers:
            data.append({
                'ID': supplier.id,
                'Name': supplier.name or '',
                'Contact Person': supplier.contact_person or '',
                'Phone': supplier.phone or '',
                'Alternate Phone': supplier.alternate_phone or '',
                'Email': supplier.email or '',
                'Address': supplier.address or '',
                'GST Number': supplier.gst_number or '',
                'Payment Terms': supplier.payment_terms or '',
                'Bank Details': str(supplier.bank_details) if supplier.bank_details else '',
                'Notes': supplier.notes or '',
                'Created At': supplier.created_at.strftime('%Y-%m-%d %H:%M:%S') if supplier.created_at else '',
                'Updated At': supplier.updated_at.strftime('%Y-%m-%d %H:%M:%S') if supplier.updated_at else ''
            })
        
        df = pd.DataFrame(data)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Suppliers', index=False)
        
        output.seek(0)
        response = make_response(output.getvalue())
        response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        response.headers['Content-Disposition'] = f'attachment; filename=suppliers_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        
        return response
    except ImportError:
        return jsonify({"error": "pandas and openpyxl are required for Excel export"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route("/<int:supplier_id>", methods=["PUT"])
@require_permission_jwt('suppliers', 'write')
@audit_decorator('suppliers', 'UPDATE')
def update_supplier(supplier_id):
    s = Supplier.query.get(supplier_id)
    if not s:
        return jsonify({"error": "Supplier not found"}), 404
    
    data = request.get_json() or {}
    try:
        s.name = data.get("name", s.name)
        s.contact_person = data.get("contact_person", s.contact_person)
        s.email = data.get("email", s.email)
        s.phone = data.get("phone", s.phone)
        s.alternate_phone = data.get("alternate_phone", s.alternate_phone)
        s.address = data.get("address", s.address)
        s.gst_number = data.get("gst_number", s.gst_number)
        s.bank_details = data.get("bank_details", s.bank_details)
        s.payment_terms = data.get("payment_terms", s.payment_terms)
        s.notes = data.get("notes", s.notes)
        
        db.session.commit()
        return jsonify({"id": s.id, "name": s.name, "phone": s.phone}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400

@bp.route("/<int:supplier_id>", methods=["DELETE"])
@require_permission_jwt('suppliers', 'write')
@audit_decorator('suppliers', 'DELETE')
def delete_supplier(supplier_id):
    s = Supplier.query.get(supplier_id)
    if not s:
        return jsonify({"error": "Supplier not found"}), 404
    
    try:
        db.session.delete(s)
        db.session.commit()
        return jsonify({"message": "Supplier deleted successfully"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400