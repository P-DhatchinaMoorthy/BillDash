from flask import Blueprint, request, jsonify
from src.extensions import db
from products.product import Product
from products.product_service import ProductService
from user.auth_bypass import require_permission
import csv
import io
import pandas as pd
from datetime import datetime

bp = Blueprint("products", __name__)

# -------------------------
# Create single or multiple products
# -------------------------
@bp.route("/", methods=["POST"])
@require_permission('products', 'write')
def create_product():
    data = request.get_json() or {}

    # Handle multiple products as a list
    if isinstance(data, list):
        created = []
        skipped = []
        errors = []

        for idx, item in enumerate(data, 1):
            if not all([item.get('id'), item.get('product_name'), item.get('sku'), item.get('purchase_price')]):
                skipped.append({"row": idx, "reason": "Missing required fields", "data": item})
                continue
            try:
                # Handle expiry_date if provided
                if item.get('expiry_date'):
                    try:
                        date_str = item['expiry_date']
                        if 'T' in str(date_str):
                            item['expiry_date'] = datetime.fromisoformat(str(date_str).replace('Z', '+00:00')).date()
                        else:
                            item['expiry_date'] = datetime.strptime(str(date_str), '%Y-%m-%d').date()
                    except ValueError:
                        errors.append({"row": idx, "error": "expiry_date must be in YYYY-MM-DD or ISO format", "data": item})
                        continue
                
                product, already_exists = ProductService.create_product(item)
                created.append({
                    "id": product.id,
                    "product_name": product.product_name,
                    "selling_price": str(product.selling_price),
                    "already_exists": already_exists
                })
            except Exception as e:
                errors.append({"row": idx, "error": str(e), "data": item})
                continue

        response = {
            "created_count": len(created),
            "skipped_count": len(skipped),
            "error_count": len(errors),
            "created": created
        }

        if skipped:
            response["skipped"] = skipped[:5]
        if errors:
            response["errors"] = errors[:5]

        return jsonify(response), 201

    # Single product
    required = ["id", "product_name", "sku", "purchase_price"]
    for r in required:
        if r not in data:
            return jsonify({"error": f"{r} is required"}), 400

    # Handle expiry_date if provided
    if data.get('expiry_date'):
        try:
            # Handle ISO format with time or just date
            date_str = data['expiry_date']
            if 'T' in str(date_str):
                data['expiry_date'] = datetime.fromisoformat(str(date_str).replace('Z', '+00:00')).date()
            else:
                data['expiry_date'] = datetime.strptime(str(date_str), '%Y-%m-%d').date()
        except ValueError:
            return jsonify({"error": "expiry_date must be in YYYY-MM-DD or ISO format"}), 400

    try:
        product, already_exists = ProductService.create_product(data)
        if already_exists:
            return jsonify({
                "message": f"Product with ID {product.id} already exists",
                "product": {"id": product.id, "product_name": product.product_name}
            }), 200
        return jsonify({"id": product.id, "selling_price": str(product.selling_price)}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# -------------------------
# Get low stock alerts (products with stock <= 100)
# -------------------------
@bp.route("/low-stock", methods=["GET"])
@require_permission('products', 'read')
def get_low_stock_alerts():
    products = Product.query.filter(Product.quantity_in_stock <= 100).order_by(Product.id.asc()).all()
    result = []
    for p in products:
        result.append({
            "id": p.id,
            "product_name": p.product_name,
            "category_id": p.category_id,
            "category_name": None,
            "quantity_in_stock": p.quantity_in_stock,
            "supplier_id": p.supplier_id,
            "sku": p.sku,
            "selling_price": str(p.selling_price),
            "purchase_price": str(p.purchase_price),
            "reorder_level": p.reorder_level
        })
    return jsonify(result), 200


# -------------------------
# List all products with optional filters
# -------------------------
@bp.route("/", methods=["GET"])
@require_permission('products', 'read')
def list_products():
    query = Product.query

    category_id = request.args.get('category_id', type=int)
    if category_id:
        query = query.filter(Product.category_id == category_id)

    subcategory_id = request.args.get('subcategory_id', type=int)
    if subcategory_id:
        query = query.filter(Product.subcategory_id == subcategory_id)

    products = query.order_by(Product.id).all()
    result = []
    for p in products:
        result.append({
            "id": p.id,
            "product_name": p.product_name,
            "description": p.description,
            "sku": p.sku,
            "category_id": p.category_id,
            "category_name": None,
            "subcategory_id": p.subcategory_id,
            "unit_of_measure": p.unit_of_measure,
            "selling_price": str(p.selling_price),
            "purchase_price": str(p.purchase_price),
            "quantity_in_stock": p.quantity_in_stock,
            "reorder_level": p.reorder_level,
            "max_stock_level": p.max_stock_level,
            "supplier_id": p.supplier_id,
            "batch_number": p.batch_number,
            "expiry_date": p.expiry_date.isoformat() if p.expiry_date else None,
            "barcode": p.barcode,
            "date_added": p.date_added.isoformat(),
            "last_updated": p.last_updated.isoformat() if p.last_updated else None
        })
    return jsonify(result), 200


# -------------------------
# Get single product by ID
# -------------------------
@bp.route("/<int:product_id>", methods=["GET"])
@require_permission('products', 'read')
def get_product(product_id):
    p = Product.query.get(product_id)
    if not p:
        return jsonify({"error": "Product not found"}), 404

    return jsonify({
        "id": p.id,
        "product_name": p.product_name,
        "description": p.description,
        "sku": p.sku,
        "category_id": p.category_id,
        "category_name": None,
        "subcategory_id": p.subcategory_id,
        "unit_of_measure": p.unit_of_measure,
        "selling_price": str(p.selling_price),
        "purchase_price": str(p.purchase_price),
        "quantity_in_stock": p.quantity_in_stock,
        "reorder_level": p.reorder_level,
        "max_stock_level": p.max_stock_level,
        "supplier_id": p.supplier_id,
        "batch_number": p.batch_number,
        "expiry_date": p.expiry_date.isoformat() if p.expiry_date else None,
        "barcode": p.barcode,
        "date_added": p.date_added.isoformat(),
        "last_updated": p.last_updated.isoformat() if p.last_updated else None
    }), 200


# -------------------------
# Update a product by ID
# -------------------------
@bp.route("/<int:product_id>", methods=["PUT"])
@require_permission('products', 'write')
def update_product(product_id):
    p = Product.query.get(product_id)
    if not p:
        return jsonify({"error": "Product not found"}), 404
    data = request.get_json() or {}
    p.product_name = data.get("product_name", p.product_name)
    p.sku = data.get("sku", p.sku)
    p.purchase_price = data.get("purchase_price", p.purchase_price)
    p.quantity_in_stock = data.get("quantity_in_stock", p.quantity_in_stock)
    p.reorder_level = data.get("reorder_level", p.reorder_level)
    p.category_id = data.get("category_id", p.category_id)
    p.subcategory_id = data.get("subcategory_id", p.subcategory_id)
    p.supplier_id = data.get("supplier_id", p.supplier_id)
    
    # Handle expiry_date update
    if 'expiry_date' in data:
        if data['expiry_date']:
            try:
                date_str = data['expiry_date']
                if 'T' in str(date_str):
                    p.expiry_date = datetime.fromisoformat(str(date_str).replace('Z', '+00:00')).date()
                else:
                    p.expiry_date = datetime.strptime(str(date_str), '%Y-%m-%d').date()
            except ValueError:
                return jsonify({"error": "expiry_date must be in YYYY-MM-DD or ISO format"}), 400
        else:
            p.expiry_date = None
    db.session.commit()
    return jsonify({"id": p.id, "product_name": p.product_name, "selling_price": str(p.selling_price)}), 200


# -------------------------
# Bulk upload products via CSV or XLSX
# -------------------------
@bp.route("/bulk", methods=["POST"])
@require_permission('products', 'write')
def bulk_upload():
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files['file']
    filename = file.filename.lower()

    if filename.endswith('.csv'):
        stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
        reader = csv.DictReader(stream)
        rows = list(reader)
    elif filename.endswith('.xlsx'):
        df = pd.read_excel(file)
        rows = df.to_dict('records')
    else:
        return jsonify({"error": "Only CSV and XLSX files supported"}), 400

    created = []
    skipped = []
    errors = []

    for i, row in enumerate(rows, 1):
        if not all([row.get('id'), row.get('product_name'), row.get('sku'), row.get('purchase_price')]):
            skipped.append({"row": i, "reason": "Missing required fields", "data": row})
            continue

        try:
            # Check if product with same SKU already exists
            sku = str(row['sku'])
            existing_product = Product.query.filter_by(sku=sku).first()
            if existing_product:
                # Update existing product instead of skipping
                existing_product.product_name = str(row['product_name'])
                existing_product.purchase_price = float(row['purchase_price'])
                existing_product.quantity_in_stock = int(row['quantity_in_stock']) if row.get('quantity_in_stock') and pd.notna(row['quantity_in_stock']) else 0
                db.session.commit()
                created.append(existing_product.id)
                continue
            
            # Validate foreign keys and set to null if not found
            category_id = int(row['category_id']) if row.get('category_id') and pd.notna(row['category_id']) else None
            supplier_id = int(row['supplier_id']) if row.get('supplier_id') and pd.notna(row['supplier_id']) else None
            
            # Check if category exists, set to null if not found
            if category_id:
                try:
                    from category.category import Category
                    if not Category.query.get(category_id):
                        category_id = None
                except ImportError:
                    category_id = None
            
            # Check if supplier exists, set to null if not found
            if supplier_id:
                try:
                    from suppliers.supplier import Supplier
                    if not Supplier.query.get(supplier_id):
                        supplier_id = None
                except ImportError:
                    supplier_id = None
            
            data = {
                "id": int(row['id']),
                "product_name": str(row['product_name']),
                "sku": str(row['sku']),
                "purchase_price": float(row['purchase_price']),
                "description": str(row['description']) if row.get('description') and pd.notna(row['description']) else None,
                "category_id": category_id,
                "subcategory_id": int(row['subcategory_id']) if row.get('subcategory_id') and pd.notna(row['subcategory_id']) else None,
                "unit_of_measure": str(row['unit_of_measure']) if row.get('unit_of_measure') and pd.notna(row['unit_of_measure']) else None,
                "quantity_in_stock": int(row['quantity_in_stock']) if row.get('quantity_in_stock') and pd.notna(row['quantity_in_stock']) else 0,
                "reorder_level": int(row['reorder_level']) if row.get('reorder_level') and pd.notna(row['reorder_level']) else None,
                "max_stock_level": int(row['max_stock_level']) if row.get('max_stock_level') and pd.notna(row['max_stock_level']) else None,
                "supplier_id": supplier_id,
                "batch_number": str(row['batch_number']) if row.get('batch_number') and pd.notna(row['batch_number']) else None,
                "expiry_date": None,
            }
            
            # Handle expiry_date separately
            if row.get('expiry_date') and pd.notna(row['expiry_date']) and str(row['expiry_date']).strip():
                try:
                    date_str = str(row['expiry_date']).strip()
                    if 'T' in date_str:
                        data['expiry_date'] = datetime.fromisoformat(date_str.replace('Z', '+00:00')).date()
                    elif '-' in date_str and len(date_str.split('-')) == 3:
                        # Handle DD-MM-YYYY format
                        parts = date_str.split('-')
                        if len(parts[0]) == 2:  # DD-MM-YYYY
                            data['expiry_date'] = datetime.strptime(date_str, '%d-%m-%Y').date()
                        else:  # YYYY-MM-DD
                            data['expiry_date'] = datetime.strptime(date_str, '%Y-%m-%d').date()
                except ValueError:
                    pass  # Keep as None if parsing fails
            
            data.update({
                "barcode": str(row['barcode']) if row.get('barcode') and pd.notna(row['barcode']) else None
            })
            product, already_exists = ProductService.create_product(data)
            created.append(product.id)
        except Exception as e:
            db.session.rollback()  # Rollback on error
            errors.append({"row": i, "error": str(e), "data": row})
            continue
    
    response = {
        "created": len(created), 
        "ids": created,
        "total_rows": len(rows),
        "skipped": len(skipped),
        "errors": len(errors)
    }
    
    if skipped or errors:
        response["details"] = {"skipped_rows": skipped[:5], "error_rows": errors[:5]}
    
    return jsonify(response), 201
