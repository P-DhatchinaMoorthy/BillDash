from flask import Blueprint, request, jsonify
from returns.return_service import ReturnService
from returns.product_return import ProductReturn, DamagedProduct
from products.product import Product
from customers.customer import Customer
from src.extensions import db
from user.auth_bypass import require_permission

return_bp = Blueprint('returns', __name__)

@return_bp.route('/returns/', methods=['POST'])
@require_permission('returns', 'write')
def create_return():
    """Create a new product return"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['product_id', 'invoice_id']
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Missing required field: {field}"}), 400
        
        # Get invoice and validate
        from invoices.invoice import Invoice
        from invoices.invoice_item import InvoiceItem
        invoice = Invoice.query.get(data['invoice_id'])
        if not invoice:
            return jsonify({"error": "Invoice not found"}), 404
        
        # Get product from invoice items
        invoice_item = InvoiceItem.query.filter_by(
            invoice_id=data['invoice_id'], 
            product_id=data['product_id']
        ).first()
        if not invoice_item:
            return jsonify({"error": "Product not found in this invoice"}), 404
        
        # Calculate unit price with tax and discount
        unit_price = float(invoice_item.unit_price)
        discount_per_item = float(invoice_item.discount_per_item or 0)
        tax_rate = float(invoice_item.tax_rate_per_item or 0)
        price_after_discount = unit_price - discount_per_item
        final_unit_price = price_after_discount * (1 + tax_rate / 100)
        
        quantity = data.get('quantity_returned', 1)
        refund_amount = round(final_unit_price * quantity, 2)
        
        # Create return data
        return_data = {
            'customer_id': invoice.customer_id,
            'product_id': data['product_id'],
            'original_invoice_id': data['invoice_id'],
            'return_type': 'return',
            'quantity_returned': quantity,
            'original_price': round(final_unit_price, 2),
            'refund_amount': refund_amount,
            'reason': data.get('reason', 'Product return'),
            'notes': data.get('notes', ''),
            'is_resaleable': True
        }
        
        # Process the return
        result = ReturnService.process_return(return_data)
        
        if result['success']:
            # Update profit and loss summary
            from reports.report_service import ReportService
            # This would update P&L - implementation depends on your P&L structure
            
            return jsonify({
                "message": "Return processed successfully",
                "return_id": result['return_id'],
                "return_number": result['return_number'],
                "refund_amount": f"{refund_amount:.2f}"
            }), 201
        else:
            return jsonify({"error": result['error']}), 400
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@return_bp.route('/returns/', methods=['GET'])
@require_permission('returns', 'read')
def get_all_returns():
    """Get all product returns with summary"""
    try:
        returns = ProductReturn.query.filter_by(return_type='return').all()
        
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
                "refund_amount": f"{float(return_item.refund_amount):.2f}" if return_item.refund_amount else "0.00",
                "status": return_item.status,
                "return_date": return_item.return_date.strftime("%Y-%m-%d %H:%M:%S"),
                "reason": return_item.notes
            })
        
        # Calculate summary statistics
        total_returns = len(returns)
        total_refund = round(sum(float(r.refund_amount or 0) for r in returns), 2)
        by_type = {
            "return": len([r for r in returns if r.return_type == 'return']),
            "exchange": len([r for r in returns if r.return_type == 'exchange']),
            "damage": len([r for r in returns if r.return_type == 'damage'])
        }
        pending_returns = len([r for r in returns if r.status == 'Pending'])
        
        return jsonify({
            "summary": {
                "total_returns": total_returns,
                "total_refund_amount": f"{total_refund:.2f}",
                "by_type": by_type,
                "pending_returns": pending_returns
            },
            "returns": returns_data
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@return_bp.route('/returns/<int:return_id>', methods=['GET'])
@require_permission('returns', 'read')
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
            "original_price": f"{float(return_item.original_price):.2f}",
            "refund_amount": f"{float(return_item.refund_amount):.2f}" if return_item.refund_amount else "0.00",
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
                "price_difference": f"{float(return_item.exchange_price_difference):.2f}"
            }
        
        # Add damage details if applicable
        if return_item.return_type == 'damage':
            return_data["damage_details"] = {
                "damage_level": return_item.damage_level,
                "is_resaleable": return_item.is_resaleable,
                "product_type": return_item.product_type
            }
        
        return jsonify(return_data), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@return_bp.route('/damaged-products/', methods=['GET'])
@require_permission('returns', 'read')
def get_damaged_products():
    """Get inventory of damaged products"""
    try:
        inventory = ReturnService.get_damaged_products_inventory()
        return jsonify(inventory), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@return_bp.route('/damaged-products/', methods=['POST'])
@require_permission('returns', 'write')
def create_damaged_product_return():
    """Create a damaged product return"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['product_id', 'invoice_id', 'type']
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Missing required field: {field}"}), 400
        
        # Validate type
        if data['type'] not in ['need refund', 'need replacement']:
            return jsonify({"error": "Type must be 'need refund' or 'need replacement'"}), 400
        
        # Get and validate invoice
        from invoices.invoice import Invoice
        from invoices.invoice_item import InvoiceItem
        invoice = Invoice.query.get(data['invoice_id'])
        if not invoice:
            return jsonify({"error": "Invoice not found"}), 404
        
        # Check payment status - must be paid
        if invoice.status != 'Paid':
            return jsonify({"error": "Payment status must be 'Paid' for damaged product returns"}), 400
        
        # Get product from invoice
        invoice_item = InvoiceItem.query.filter_by(
            invoice_id=data['invoice_id'], 
            product_id=data['product_id']
        ).first()
        if not invoice_item:
            return jsonify({"error": "Product not found in this invoice"}), 404
        
        # Calculate refund amount
        unit_price = float(invoice_item.unit_price)
        discount_per_item = float(invoice_item.discount_per_item or 0)
        tax_rate = float(invoice_item.tax_rate_per_item or 0)
        price_after_discount = unit_price - discount_per_item
        final_unit_price = price_after_discount * (1 + tax_rate / 100)
        quantity = data.get('quantity_returned', 1)
        refund_amount = round(final_unit_price * quantity, 2)
        
        # Create return data
        return_data = {
            'customer_id': invoice.customer_id,
            'product_id': data['product_id'],
            'original_invoice_id': data['invoice_id'],
            'return_type': 'damage',
            'product_type': 'refund' if data['type'] == 'need refund' else 'replacement',
            'quantity_returned': quantity,
            'original_price': round(final_unit_price, 2),
            'refund_amount': refund_amount if data['type'] == 'need refund' else 0,
            'damage_level': data.get('damage_level', 'Major'),
            'reason': f"Damaged product - {data['type']}",
            'notes': data.get('notes', '')
        }
        
        # Process the return
        result = ReturnService.process_return(return_data)
        
        if result['success']:
            # Update profit and loss for refunds
            if data['type'] == 'need refund':
                from reports.report_service import ReportService
                # This would update P&L - implementation depends on your P&L structure
                pass
            
            return jsonify({
                "message": f"Damaged product return processed successfully - {data['type']}",
                "return_id": result['return_id'],
                "return_number": result['return_number'],
                "refund_amount": f"{refund_amount:.2f}" if data['type'] == 'need refund' else "0.00"
            }), 201
        else:
            return jsonify({"error": result['error']}), 400
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@return_bp.route('/adjustments/', methods=['GET'])
@require_permission('returns', 'read')
def get_adjustments():
    """Get all product adjustments"""
    try:
        # Get all exchange type returns as adjustments
        adjustments = ProductReturn.query.filter_by(return_type='exchange').all()
        
        adjustments_data = []
        for adj in adjustments:
            old_price = float(adj.original_price or 0)
            new_price = 0
            if adj.exchange_product_id and adj.exchange_product:
                new_price = float(adj.exchange_product.selling_price or 0)
            
            price_diff = float(adj.exchange_price_difference or 0)
            old_total = old_price * adj.quantity_returned
            new_total = new_price * adj.exchange_quantity
            
            who_pays = "No payment needed"
            if price_diff > 0:
                who_pays = "Customer pays us"
            elif price_diff < 0:
                who_pays = "We pay customer"
            
            adjustments_data.append({
                "id": adj.id,
                "return_number": adj.return_number,
                "customer_id": adj.customer_id,
                "customer_name": adj.customer.contact_person if adj.customer else None,
                "old_product": {
                    "id": adj.product_id,
                    "name": adj.product.product_name if adj.product else None,
                    "unit_price": f"{old_price:.2f}",
                    "quantity": adj.quantity_returned,
                    "total_amount": f"{old_total:.2f}"
                },
                "new_product": {
                    "id": adj.exchange_product_id,
                    "name": adj.exchange_product.product_name if adj.exchange_product else None,
                    "unit_price": f"{new_price:.2f}",
                    "quantity": adj.exchange_quantity,
                    "total_amount": f"{new_total:.2f}"
                },
                "price_breakdown": {
                    "difference_amount": f"{abs(price_diff):.2f}",
                    "who_pays": who_pays,
                    "payment_direction": "Customer to Us" if price_diff > 0 else "Us to Customer" if price_diff < 0 else "No payment"
                },
                "adjustment_date": adj.return_date.strftime("%Y-%m-%d %H:%M:%S"),
                "status": adj.status,
                "notes": adj.notes
            })
        
        total_customer_pays = sum(float(a.exchange_price_difference or 0) for a in adjustments if float(a.exchange_price_difference or 0) > 0)
        total_we_pay = sum(abs(float(a.exchange_price_difference or 0)) for a in adjustments if float(a.exchange_price_difference or 0) < 0)
        
        return jsonify({
            "summary": {
                "total_adjustments": len(adjustments),
                "total_customer_pays_us": f"{total_customer_pays:.2f}",
                "total_we_pay_customer": f"{total_we_pay:.2f}",
                "net_amount": f"{(total_customer_pays - total_we_pay):.2f}"
            },
            "adjustments": adjustments_data
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@return_bp.route('/adjustments/', methods=['POST'])
@require_permission('returns', 'write')
def create_adjustment():
    """Create a product adjustment/exchange"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['product_id', 'invoice_id', 'new_product_id']
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Missing required field: {field}"}), 400
        
        # Get and validate invoice
        from invoices.invoice import Invoice
        from invoices.invoice_item import InvoiceItem
        invoice = Invoice.query.get(data['invoice_id'])
        if not invoice:
            return jsonify({"error": "Invoice not found"}), 404
        
        # Check payment status - must be paid
        if invoice.status != 'Paid':
            return jsonify({"error": "Payment status must be 'Paid' for adjustments"}), 400
        
        # Get old product from invoice
        invoice_item = InvoiceItem.query.filter_by(
            invoice_id=data['invoice_id'], 
            product_id=data['product_id']
        ).first()
        if not invoice_item:
            return jsonify({"error": "Product not found in this invoice"}), 404
        
        # Get new product
        new_product = Product.query.get(data['new_product_id'])
        if not new_product:
            return jsonify({"error": "New product not found"}), 404
        
        # Calculate price difference
        old_unit_price = float(invoice_item.unit_price)
        old_discount = float(invoice_item.discount_per_item or 0)
        old_tax_rate = float(invoice_item.tax_rate_per_item or 0)
        old_final_price = (old_unit_price - old_discount) * (1 + old_tax_rate / 100)
        
        new_unit_price = float(new_product.selling_price or 0)
        quantity = data.get('quantity_returned', 1)
        exchange_quantity = data.get('exchange_quantity', quantity)
        
        price_difference = round((new_unit_price * exchange_quantity) - (old_final_price * quantity), 2)
        
        # Create return data for exchange
        return_data = {
            'customer_id': invoice.customer_id,
            'product_id': data['product_id'],
            'original_invoice_id': data['invoice_id'],
            'return_type': 'exchange',
            'quantity_returned': quantity,
            'original_price': round(old_final_price, 2),
            'exchange_product_id': data['new_product_id'],
            'exchange_quantity': exchange_quantity,
            'exchange_price_difference': abs(price_difference),
            'refund_amount': abs(price_difference) if price_difference < 0 else 0,
            'reason': 'Product adjustment/exchange',
            'notes': data.get('notes', ''),
            'is_resaleable': True
        }
        
        # Process the return
        result = ReturnService.process_return(return_data)
        
        if result['success']:
            payment_message = ""
            display_difference = abs(price_difference)
            if price_difference > 0:
                payment_message = f"Customer needs to pay additional ₹{display_difference:.2f}"
            elif price_difference < 0:
                payment_message = f"Refund ₹{display_difference:.2f} to customer"
            else:
                payment_message = "No additional payment required"
            
            return jsonify({
                "message": "Product adjustment processed successfully",
                "return_id": result['return_id'],
                "return_number": result['return_number'],
                "price_difference": f"{display_difference:.2f}",
                "payment_message": payment_message
            }), 201
        else:
            return jsonify({"error": result['error']}), 400
            
    except Exception as e:
        return jsonify({"error": str(e)}),
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500