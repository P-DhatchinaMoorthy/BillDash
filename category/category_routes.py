from flask import Blueprint, request, jsonify
from extensions import db
from category.category import Category
import io
import pandas as pd

bp = Blueprint("categories", __name__)


@bp.route("/", methods=["POST"])
def create_category():
    data = request.get_json() or {}
    if not data.get("name"):
        return jsonify({"error": "name is required"}), 400

    # Get next ID
    last_category = Category.query.order_by(Category.id.desc()).first()
    next_id = (last_category.id + 1) if last_category and last_category.id >= 1001 else 1001
    
    c = Category(
        id=next_id,
        name=data["name"],
        description=data.get("description"),
        subcategory_id=data.get("subcategory_id"),
        subcategory_name=data.get("subcategory_name")
    )
    db.session.add(c)
    db.session.commit()
    return jsonify({"id": c.id, "name": c.name}), 201


@bp.route("/", methods=["GET"])
def list_categories():
    cats = Category.query.all()
    return jsonify([
        {
            "id": c.id,
            "name": c.name,
            "description": c.description,
            "subcategory_id": c.subcategory_id,
            "subcategory_name": c.subcategory_name,
        } for c in cats
    ]), 200


@bp.route("/<int:category_id>", methods=["GET"])
def get_category(category_id):
    # Check categories first
    c = Category.query.get(category_id)
    if c:
        return jsonify({
            "category_id": c.id,
            "category_name": c.name,
            "description": c.description,
            "subcategory_id": c.subcategory_id,
            "subcategory_name": c.subcategory_name,
            "type": "category"
        }), 200

    sub = Category.query.filter_by(subcategory_id=category_id).first()
    if sub:
        return jsonify({
            "subcategory_id": sub.subcategory_id,
            "subcategory_name": sub.subcategory_name,
            "description": sub.description,
            "category_id": sub.id,
            "category_name": sub.name,
            "type": "subcategory"
        }), 200
    
    return jsonify({"error": "Not found"}), 404


@bp.route("/<int:category_id>", methods=["PUT"])
def update_category(category_id):
    c = Category.query.get(category_id)
    if not c:
        return jsonify({"error": "Not found"}), 404

    data = request.get_json() or {}
    c.name = data.get("name", c.name)
    c.description = data.get("description", c.description)
    db.session.commit()
    return jsonify({"id": c.id, "name": c.name}), 200


@bp.route("/bulk", methods=["POST"])
def bulk_upload():
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

        # Validate required columns
        required_cols = ['name']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            return jsonify({"error": f"Missing columns: {missing_cols}"}), 400

        results = []
        success_count = 0
        
        for index, row in df.iterrows():
            try:
                if Category.query.filter_by(name=str(row['name'])).first():
                    results.append({
                        "row": index + 1,
                        "status": "error",
                        "error": "Category name already exists"
                    })
                    continue
                
                # Get next ID
                last_category = Category.query.order_by(Category.id.desc()).first()
                next_id = (last_category.id + 1) if last_category and last_category.id >= 1001 else 1001
                
                category_data = {
                    'id': next_id,
                    'name': str(row['name'])
                }
                
                for field in ['description', 'subcategory_name']:
                    if field in row and pd.notna(row[field]):
                        category_data[field] = str(row[field])
                
                if 'subcategory_id' in row and pd.notna(row['subcategory_id']):
                    category_data['subcategory_id'] = int(row['subcategory_id'])
                
                category = Category(**category_data)
                db.session.add(category)
                db.session.commit()
                
                results.append({
                    "row": index + 1,
                    "status": "success",
                    "category_id": category.id,
                    "name": category.name
                })
                success_count += 1
                
            except Exception as e:
                db.session.rollback()
                results.append({
                    "row": index + 1,
                    "status": "error",
                    "error": str(e)
                })
        
        return jsonify({
            "success_count": success_count,
            "total_rows": len(df),
            "results": results
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
