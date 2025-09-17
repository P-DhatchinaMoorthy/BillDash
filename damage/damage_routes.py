from flask import Blueprint, request, jsonify, make_response
from datetime import datetime
from damage.supplier_return import SupplierReturn
from returns.product_return import DamagedProduct
from products.product import Product
from suppliers.supplier import Supplier
from stock_transactions.stock_transaction import StockTransaction
from src.extensions import db
from user.enhanced_auth_middleware import require_permission_jwt
from user.audit_logger import audit_decorator
import csv
import io

damage_bp = Blueprint('damage', __name__)

@damage_bp.route('/return-to-supplier/', methods=['POST'])
@require_permission_jwt('damage', 'write')
@audit_decorator('damage', 'RETURN_TO_SUPPLIER')
def return_damaged_to_supplier():
    """Return damaged product to supplier"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['damaged_product_id', 'return_type']
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Missing required field: {field}"}), 400
        
        # Validate return_type
        if data['return_type'] not in ['refund', 'replacement']:
            return jsonify({"error": "return_type must be 'refund' or 'replacement'"}), 400
        
        # Get damaged product
        damaged_product = DamagedProduct.query.get(data['damaged_product_id'])
        if not damaged_product:
            return jsonify({"error": "Damaged product not found"}), 404
        
        # Check if already returned to supplier
        if damaged_product.status == "Returned to Supplier":
            return jsonify({"error": "This damaged product has already been returned to supplier"}), 400
        
        # Get supplier_id from damaged product's purchase history if not provided
        supplier_id = data.get('supplier_id')
        if not supplier_id:
            # Find supplier from purchase history
            purchase = StockTransaction.query.filter_by(
                product_id=damaged_product.product_id,
                transaction_type='Purchase'
            ).order_by(StockTransaction.transaction_date.desc()).first()
            
            if not purchase or not purchase.supplier_id:
                return jsonify({"error": "Cannot determine supplier. Please provide supplier_id"}), 400
            
            supplier_id = purchase.supplier_id
        
        # Validate supplier exists
        supplier = Supplier.query.get(supplier_id)
        if not supplier:
            return jsonify({"error": "Supplier not found"}), 404
        
        # Calculate refund amount if refund type
        refund_amount = 0
        if data['return_type'] == 'refund':
            product = Product.query.get(damaged_product.product_id)
            if product:
                refund_amount = float(product.purchase_price or 0) * damaged_product.quantity
        
        # Create supplier return record
        supplier_return = SupplierReturn(
            damaged_product_id=data['damaged_product_id'],
            supplier_id=supplier_id,
            return_type=data['return_type'],
            quantity_returned=damaged_product.quantity,
            refund_amount=refund_amount,
            notes=data.get('notes', '')
        )
        
        db.session.add(supplier_return)
        
        # Update damaged product status
        damaged_product.status = "Returned to Supplier"
        damaged_product.action_taken = "Return_to_Supplier"
        damaged_product.action_date = datetime.utcnow()
        
        # If replacement, add quantity back to stock immediately
        if data['return_type'] == 'replacement':
            product = Product.query.get(damaged_product.product_id)
            if product:
                product.quantity_in_stock += damaged_product.quantity
        
        db.session.commit()
        
        return jsonify({
            "message": f"Damaged product returned to supplier for {data['return_type']}",
            "supplier_return_id": supplier_return.id,
            "return_number": supplier_return.return_number,
            "refund_amount": f"{refund_amount:.2f}" if data['return_type'] == 'refund' else "0.00"
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@damage_bp.route('/supplier-returns/', methods=['GET'])
@require_permission_jwt('damage', 'read')
def get_supplier_returns():
    """Get all supplier returns"""
    try:
        export_format = request.args.get('export')
        returns = SupplierReturn.query.all()
        
        returns_data = []
        for ret in returns:
            supplier = Supplier.query.get(ret.supplier_id)
            damaged_product = ret.damaged_product
            product = Product.query.get(damaged_product.product_id) if damaged_product else None
            
            returns_data.append({
                "id": ret.id,
                "return_number": ret.return_number,
                "damaged_product_id": ret.damaged_product_id,
                "supplier": {
                    "id": supplier.id,
                    "name": supplier.name,
                    "contact_person": supplier.contact_person
                } if supplier else None,
                "product": {
                    "id": product.id,
                    "name": product.product_name,
                    "sku": product.sku
                } if product else None,
                "return_type": ret.return_type,
                "quantity_returned": ret.quantity_returned,
                "refund_amount": f"{float(ret.refund_amount):.2f}" if ret.refund_amount else "0.00",
                "status": ret.status,
                "return_date": ret.return_date.strftime("%Y-%m-%d %H:%M:%S"),
                "notes": ret.notes
            })
        
        if export_format == 'csv':
            output = io.StringIO()
            writer = csv.writer(output)
            
            # CSV headers
            writer.writerow(['Return Number', 'Product Name', 'SKU', 'Supplier Name', 'Return Type', 
                           'Quantity', 'Refund Amount', 'Status', 'Return Date', 'Notes'])
            
            # CSV data
            for ret in returns_data:
                writer.writerow([
                    ret['return_number'],
                    ret['product']['name'] if ret['product'] else '',
                    ret['product']['sku'] if ret['product'] else '',
                    ret['supplier']['name'] if ret['supplier'] else '',
                    ret['return_type'],
                    ret['quantity_returned'],
                    ret['refund_amount'],
                    ret['status'],
                    ret['return_date'],
                    ret['notes'] or ''
                ])
            
            response = make_response(output.getvalue())
            response.headers['Content-Type'] = 'text/csv'
            response.headers['Content-Disposition'] = f'attachment; filename=supplier_returns_{datetime.now().strftime("%Y%m%d")}.csv'
            return response
        
        return jsonify({
            "total_returns": len(returns),
            "returns": returns_data
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@damage_bp.route('/receive-replacement/', methods=['POST'])
@require_permission_jwt('damage', 'write')
@audit_decorator('damage', 'RECEIVE_REPLACEMENT')
def receive_replacement_from_supplier():
    """Receive replacement product from supplier and add to stock"""
    try:
        data = request.get_json()
        
        # Validate required fields
        if 'supplier_return_id' not in data:
            return jsonify({"error": "Missing required field: supplier_return_id"}), 400
        
        # Get supplier return record
        supplier_return = SupplierReturn.query.get(data['supplier_return_id'])
        if not supplier_return:
            return jsonify({"error": "Supplier return not found"}), 404
        
        # Check if it's a replacement type
        if supplier_return.return_type != 'replacement':
            return jsonify({"error": "This return is not for replacement"}), 400
        
        # Check if already received
        if supplier_return.status == 'Completed':
            return jsonify({"error": "Replacement already received"}), 400
        
        # Get the damaged product and original product
        damaged_product = supplier_return.damaged_product
        if not damaged_product:
            return jsonify({"error": "Associated damaged product not found"}), 404
        
        product = Product.query.get(damaged_product.product_id)
        if not product:
            return jsonify({"error": "Original product not found"}), 404
        
        # Add replacement quantity back to stock
        product.quantity_in_stock += supplier_return.quantity_returned
        
        # Create stock transaction for replacement received
        stock_transaction = StockTransaction(
            product_id=product.id,
            transaction_type='Purchase',
            quantity=supplier_return.quantity_returned,
            supplier_id=supplier_return.supplier_id,
            reference_number=supplier_return.return_number,
            notes=f"Replacement received for damaged product return {supplier_return.return_number}"
        )
        
        db.session.add(stock_transaction)
        
        # Update supplier return status
        supplier_return.status = 'Completed'
        supplier_return.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            "message": "Replacement product received and added to stock",
            "product_id": product.id,
            "product_name": product.product_name,
            "quantity_added": supplier_return.quantity_returned,
            "new_stock_quantity": product.quantity_in_stock,
            "return_number": supplier_return.return_number
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@damage_bp.route('/pending-replacements/', methods=['GET'])
@require_permission_jwt('damage', 'read')
def get_pending_replacements():
    """Get all pending replacement returns from suppliers"""
    try:
        pending_returns = SupplierReturn.query.filter_by(
            return_type='replacement',
            status='Sent'
        ).all()
        
        pending_data = []
        for ret in pending_returns:
            supplier = Supplier.query.get(ret.supplier_id)
            damaged_product = ret.damaged_product
            product = Product.query.get(damaged_product.product_id) if damaged_product else None
            
            pending_data.append({
                "supplier_return_id": ret.id,
                "return_number": ret.return_number,
                "supplier": {
                    "id": supplier.id,
                    "name": supplier.name
                } if supplier else None,
                "product": {
                    "id": product.id,
                    "name": product.product_name,
                    "sku": product.sku
                } if product else None,
                "quantity_expected": ret.quantity_returned,
                "return_date": ret.return_date.strftime("%Y-%m-%d %H:%M:%S"),
                "notes": ret.notes
            })
        
        return jsonify({
            "total_pending": len(pending_returns),
            "pending_replacements": pending_data
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500