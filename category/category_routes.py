from flask import Blueprint, request, jsonify, send_file
from src.extensions import db
from category.category import Category
from user.enhanced_auth_middleware import require_permission_jwt
from user.audit_logger import audit_decorator
import io
import pandas as pd
from datetime import datetime

bp = Blueprint("categories", __name__)


@bp.route("/", methods=["POST"])
@require_permission_jwt('categories', 'write')
@audit_decorator('categories', 'CREATE')
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
        subcategory_name=data.get("subcategory_name"),
        hsn_code=data.get("hsn_code"),
        cgst_rate=data.get("cgst_rate", 0),
        sgst_rate=data.get("sgst_rate", 0),
        igst_rate=data.get("igst_rate", 0)
    )
    db.session.add(c)
    db.session.commit()
    return jsonify({"id": c.id, "name": c.name}), 201


@bp.route("/", methods=["GET"])
@require_permission_jwt('categories', 'read')
def list_categories():
    cats = Category.query.all()
    return jsonify([
        {
            "id": c.id,
            "name": c.name,
            "description": c.description,
            "subcategory_id": c.subcategory_id,
            "subcategory_name": c.subcategory_name,
            "hsn_code": c.hsn_code,
            "cgst_rate": str(c.cgst_rate),
            "sgst_rate": str(c.sgst_rate),
            "igst_rate": str(c.igst_rate)
        } for c in cats
    ]), 200


@bp.route("/<int:category_id>", methods=["GET"])
@require_permission_jwt('categories', 'read')
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
            "hsn_code": c.hsn_code,
            "cgst_rate": str(c.cgst_rate),
            "sgst_rate": str(c.sgst_rate),
            "igst_rate": str(c.igst_rate),
            "type": "category"
        }), 200

    sub = Category.query.filter_by(subcategory_id=category_id).first()
    if sub:
        return jsonify({
            "subcategory_id": sub.subcategory_id,
            "subcategory_name": sub.subcategory_name,
            "description": sub.description,
            "hsn_code": sub.hsn_code,
            "cgst_rate": str(sub.cgst_rate),
            "sgst_rate": str(sub.sgst_rate),
            "igst_rate": str(sub.igst_rate),
            "category_id": sub.id,
            "category_name": sub.name,
            "type": "subcategory"

        }), 200
    
    return jsonify({"error": "Not found"}), 404


@bp.route("/<int:category_id>", methods=["PUT"])
@require_permission_jwt('categories', 'write')
@audit_decorator('categories', 'UPDATE')
def update_category(category_id):
    c = Category.query.get(category_id)
    if not c:
        return jsonify({"error": "Not found"}), 404

    data = request.get_json() or {}
    c.name = data.get("name", c.name)
    c.description = data.get("description", c.description)
    c.hsn_code = data.get("hsn_code", c.hsn_code)
    c.cgst_rate = data.get("cgst_rate", c.cgst_rate)
    c.sgst_rate = data.get("sgst_rate", c.sgst_rate)
    c.igst_rate = data.get("igst_rate", c.igst_rate)
    db.session.commit()
    return jsonify({"id": c.id, "name": c.name}), 200


@bp.route("/bulk", methods=["POST"])
@require_permission_jwt('categories', 'write')
@audit_decorator('categories', 'BULK_IMPORT')
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
                
                for field in ['description', 'subcategory_name', 'hsn_code']:
                    if field in row and pd.notna(row[field]):
                        category_data[field] = str(row[field])
                
                if 'subcategory_id' in row and pd.notna(row['subcategory_id']):
                    category_data['subcategory_id'] = int(row['subcategory_id'])
                
                for field in ['cgst_rate', 'sgst_rate', 'igst_rate']:
                    if field in row and pd.notna(row[field]):
                        category_data[field] = float(row[field])
                
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


@bp.route("/export/excel", methods=["GET"])
@require_permission_jwt('categories', 'read')
@audit_decorator('categories', 'EXPORT_EXCEL')
def export_categories_excel():
    try:
        cats = Category.query.all()
        data = []
        for c in cats:
            data.append({
                "ID": c.id,
                "Name": c.name,
                "Description": c.description,
                "Subcategory ID": c.subcategory_id,
                "Subcategory Name": c.subcategory_name,
                "HSN Code": c.hsn_code,
                "CGST Rate": float(c.cgst_rate) if c.cgst_rate else 0,
                "SGST Rate": float(c.sgst_rate) if c.sgst_rate else 0,
                "IGST Rate": float(c.igst_rate) if c.igst_rate else 0,
                "Created At": c.created_at.strftime('%Y-%m-%d %H:%M:%S') if c.created_at else ''
            })
        
        df = pd.DataFrame(data)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Categories')
        output.seek(0)
        
        filename = f"categories_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/export/csv", methods=["GET"])
@require_permission_jwt('categories', 'read')
@audit_decorator('categories', 'EXPORT_CSV')
def export_categories_csv():
    try:
        cats = Category.query.all()
        data = []
        for c in cats:
            data.append({
                "ID": c.id,
                "Name": c.name,
                "Description": c.description,
                "Subcategory ID": c.subcategory_id,
                "Subcategory Name": c.subcategory_name,
                "HSN Code": c.hsn_code,
                "CGST Rate": float(c.cgst_rate) if c.cgst_rate else 0,
                "SGST Rate": float(c.sgst_rate) if c.sgst_rate else 0,
                "IGST Rate": float(c.igst_rate) if c.igst_rate else 0,
                "Created At": c.created_at.strftime('%Y-%m-%d %H:%M:%S') if c.created_at else ''
            })
        
        df = pd.DataFrame(data)
        output = io.StringIO()
        df.to_csv(output, index=False)
        output.seek(0)
        
        filename = f"categories_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/<int:category_id>", methods=["DELETE"])
@require_permission_jwt('categories', 'write')
@audit_decorator('categories', 'DELETE')
def delete_category(category_id):
    c = Category.query.get(category_id)
    if not c:
        return jsonify({"error": "Category not found"}), 404
    
    try:
        db.session.delete(c)
        db.session.commit()
        return jsonify({"message": "Category deleted successfully"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400
