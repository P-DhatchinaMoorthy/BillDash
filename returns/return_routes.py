from flask import Blueprint, request, jsonify
from returns.return_service import ReturnService
from returns.product_return import ProductReturn, DamagedProduct
from products.product import Product
from customers.customer import Customer
from extensions import db

return_bp = Blueprint('returns', __name__)

@return_bp.route('/returns/', methods=['POST'])
def create_return():
    """Create a new product return"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['invoice_id', 'product_id', 'return_type', 'quantity_returned']
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Missing required field: {field}"}), 400
        
        # Get invoice and validate
        from invoices.invoice import Invoice
        from invoices.invoice_item import InvoiceItem
        invoice = Invoice.query.get(data['invoice_id'])
        if not invoice:
            return jsonify({"error": "Invoice not found"}), 404
        
        # Check payment status - prevent returns if payment is due, partially paid, or pending
        is_valid, error_message = ReturnService.validate_payment_status(invoice)
        if not is_valid:
            return jsonify({"error": error_message}), 400
        
        # Get product from invoice items
        invoice_item = InvoiceItem.query.filter_by(
            invoice_id=data['invoice_id'], 
            product_id=data['product_id']
        ).first()
        if not invoice_item:
            return jsonify({"error": "Product not found in this invoice"}), 404
        
        # Check total returned quantity for this invoice + product combination
        existing_returns = ProductReturn.query.filter_by(
            original_invoice_id=data['invoice_id'],
            product_id=data['product_id']
        ).all()
        
        total_already_returned = sum([r.quantity_returned for r in existing_returns])
        total_after_this_return = total_already_returned + data['quantity_returned']
        
        # Validate return quantity doesn't exceed invoice quantity
        if total_after_this_return > invoice_item.quantity:
            return jsonify({
                "error": f"Cannot return {data['quantity_returned']} items. Invoice contains {invoice_item.quantity} of this product, but {total_already_returned} already returned. Maximum returnable: {invoice_item.quantity - total_already_returned}"
            }), 400
        
        # Calculate unit price with tax and discount
        unit_price = float(invoice_item.unit_price)
        discount_per_item = float(invoice_item.discount_per_item or 0)
        tax_rate = float(invoice_item.tax_rate_per_item or 0)
        
        # Price after discount, before tax
        price_after_discount = unit_price - discount_per_item
        # Price with tax
        final_unit_price = price_after_discount * (1 + tax_rate / 100)
        
        # Auto-populate fields from invoice
        data['customer_id'] = invoice.customer_id
        data['original_price'] = final_unit_price
        data['original_invoice_id'] = data.pop('invoice_id')
        
        # Auto-calculate refund amount if not provided
        if 'refund_amount' not in data or data['refund_amount'] == 0:
            data['refund_amount'] = final_unit_price * data['quantity_returned']
        
        # Validate return type
        if data['return_type'] not in ['return', 'exchange', 'damage']:
            return jsonify({"error": "Invalid return_type. Must be 'return', 'exchange', or 'damage'"}), 400
        
        # Process the return
        result = ReturnService.process_return(data)
        
        if result['success']:
            return jsonify({
                "message": "Return processed successfully",
                "return_id": result['return_id'],
                "return_number": result['return_number']
            }), 201
        else:
            return jsonify({"error": result['error']}), 400
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@return_bp.route('/returns/', methods=['GET'])
def get_all_returns():
    """Get all product returns with summary"""
    try:
        returns = ProductReturn.query.all()
        
        returns_data = []
        for return_item in returns:
            returns_data.append({
                "id": return_item.id,
                "return_number": return_item.return_number,
                "customer_id": return_item.customer_id,
                "customer_name": return_item.customer.contact_person if return_item.customer else None,
                "product_id": return_item.product_id,
                "product_name": return_item.product.product_name,
                "return_type": return_item.return_type,
                "quantity_returned": return_item.quantity_returned,
                "refund_amount": float(return_item.refund_amount) if return_item.refund_amount else 0,
                "status": return_item.status,
                "return_date": return_item.return_date.strftime("%Y-%m-%d %H:%M:%S"),
                "reason": return_item.notes
            })
        
        # Calculate summary statistics
        total_returns = len(returns)
        total_refund = sum(float(r.refund_amount or 0) for r in returns)
        by_type = {
            "return": len([r for r in returns if r.return_type == 'return']),
            "exchange": len([r for r in returns if r.return_type == 'exchange']),
            "damage": len([r for r in returns if r.return_type == 'damage'])
        }
        pending_returns = len([r for r in returns if r.status == 'Pending'])
        
        return jsonify({
            "summary": {
                "total_returns": total_returns,
                "total_refund_amount": total_refund,
                "by_type": by_type,
                "pending_returns": pending_returns
            },
            "returns": returns_data
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@return_bp.route('/returns/summary', methods=['GET'])
def get_returns_summary():
    """Get returns summary with statistics"""
    try:
        summary = ReturnService.get_return_summary()
        return jsonify(summary), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@return_bp.route('/returns/<int:return_id>', methods=['GET'])
def get_return_details(return_id):
    """Get details of a specific return"""
    try:
        return_item = ProductReturn.query.get_or_404(return_id)
        
        return_data = {
            "id": return_item.id,
            "return_number": return_item.return_number,
            "customer": {
                "id": return_item.customer_id,
                "name": return_item.customer.contact_person if return_item.customer else None
            },
            "product": {
                "id": return_item.product_id,
                "name": return_item.product.product_name,
                "sku": return_item.product.sku
            },
            "return_type": return_item.return_type,
            "quantity_returned": return_item.quantity_returned,
            "original_price": float(return_item.original_price),
            "refund_amount": float(return_item.refund_amount) if return_item.refund_amount else 0,
            "status": return_item.status,
            "return_date": return_item.return_date.strftime("%Y-%m-%d %H:%M:%S"),
            "reason": return_item.reason,
            "notes": return_item.notes
        }
        
        # Add exchange details if applicable
        if return_item.return_type == 'exchange' and return_item.exchange_product_id:
            return_data["exchange_product"] = {
                "id": return_item.exchange_product_id,
                "name": return_item.exchange_product.product_name,
                "quantity": return_item.exchange_quantity,
                "price_difference": float(return_item.exchange_price_difference)
            }
        
        # Add damage details if applicable
        if return_item.return_type == 'damage':
            return_data["damage_details"] = {
                "damage_level": return_item.damage_level,
                "is_resaleable": return_item.is_resaleable
            }
        
        return jsonify(return_data), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@return_bp.route('/returns/<int:return_id>/summary', methods=['GET'])
def get_return_summary(return_id):
    """Get detailed summary for a specific return"""
    try:
        return_item = ProductReturn.query.get_or_404(return_id)
        
        summary = {
            "return_details": {
                "id": return_item.id,
                "return_number": return_item.return_number,
                "return_type": return_item.return_type,
                "quantity_returned": return_item.quantity_returned,
                "refund_amount": float(return_item.refund_amount) if return_item.refund_amount else 0,
                "status": return_item.status,
                "return_date": return_item.return_date.strftime("%Y-%m-%d %H:%M:%S"),
                "reason": return_item.reason,
                "notes": return_item.notes
            },
            "customer_details": {
                "id": return_item.customer_id,
                "name": return_item.customer.contact_person if return_item.customer else "Unknown",
                "phone": return_item.customer.phone if return_item.customer else None,
                "email": return_item.customer.email if return_item.customer else None,
                "billing_address": return_item.customer.billing_address if return_item.customer else None
            },
            "invoice_details": {
                "id": return_item.original_invoice_id,
                "invoice_number": return_item.original_invoice.invoice_number if return_item.original_invoice else None,
                "invoice_date": return_item.original_invoice.invoice_date.strftime("%Y-%m-%d") if return_item.original_invoice else None,
                "grand_total": float(return_item.original_invoice.grand_total) if return_item.original_invoice else 0,
                "payment_terms": return_item.original_invoice.payment_terms if return_item.original_invoice else None,
                "status": return_item.original_invoice.status if return_item.original_invoice else None
            },
            "product_details": {
                "id": return_item.product_id,
                "name": return_item.product.product_name if return_item.product else "Unknown",
                "sku": return_item.product.sku if return_item.product else None,
                "original_price": float(return_item.original_price),
                "category": return_item.product.category_id if return_item.product else None
            }
        }
        
        return jsonify(summary), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@return_bp.route('/returns/summary', methods=['GET'])
def get_all_returns_summary():
    """Get basic summary statistics of all returns"""
    try:
        returns = ProductReturn.query.all()
        
        summary = {
            "total_returns": len(returns),
            "by_type": {
                "return": len([r for r in returns if r.return_type == 'return']),
                "exchange": len([r for r in returns if r.return_type == 'exchange']),
                "damage": len([r for r in returns if r.return_type == 'damage'])
            },
            "total_refund_amount": float(sum([r.refund_amount for r in returns if r.refund_amount])),
            "pending_returns": len([r for r in returns if r.status == 'Pending'])
        }
        
        return jsonify(summary), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@return_bp.route('/returns/damage', methods=['GET'])
def get_damage_returns():
    """Get all damage returns with replacement invoices"""
    try:
        damage_returns = ProductReturn.query.filter_by(return_type='damage').all()
        
        damage_data = []
        for return_item in damage_returns:
            damage_info = {
                "return_id": return_item.id,
                "return_number": return_item.return_number,
                "original_invoice_id": return_item.original_invoice_id,
                "customer_name": return_item.customer.full_name if return_item.customer else "Unknown",
                "product_name": return_item.product.product_name if return_item.product else "Unknown",
                "quantity_damaged": return_item.quantity_returned,
                "damage_level": return_item.damage_level,
                "replacement_sent": return_item.exchange_quantity > 0,
                "replacement_quantity": return_item.exchange_quantity,
                "return_date": return_item.return_date.strftime("%Y-%m-%d %H:%M:%S"),
                "reason": return_item.reason,
                "notes": return_item.notes
            }
            damage_data.append(damage_info)
        
        return jsonify({
            "total_damage_returns": len(damage_returns),
            "damage_returns": damage_data
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@return_bp.route('/damaged-products/', methods=['GET'])
def get_damaged_products():
    """Get inventory of damaged products"""
    try:
        inventory = ReturnService.get_damaged_products_inventory()
        return jsonify(inventory), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@return_bp.route('/damaged-products/<int:damaged_id>/action', methods=['PUT'])
def update_damaged_product_action(damaged_id):
    """Update action taken on damaged product"""
    try:
        data = request.get_json()
        damaged_product = DamagedProduct.query.get_or_404(damaged_id)
        
        # Update action details
        if 'action_taken' in data:
            damaged_product.action_taken = data['action_taken']
        if 'repair_cost' in data:
            damaged_product.repair_cost = data['repair_cost']
        if 'status' in data:
            damaged_product.status = data['status']
        
        damaged_product.action_date = db.func.now()
        
        db.session.commit()
        
        return jsonify({"message": "Damaged product action updated successfully"}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500