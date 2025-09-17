from flask import Blueprint, request, jsonify, send_file, make_response
from returns.return_service import ReturnService
from returns.product_return import ProductReturn, DamagedProduct
from products.product import Product
from customers.customer import Customer
from src.extensions import db
from user.enhanced_auth_middleware import require_permission_jwt
from user.audit_logger import audit_decorator
import pandas as pd
import io
from datetime import datetime

return_bp = Blueprint('returns', __name__)

@return_bp.route('/returns/', methods=['POST'])
@require_permission_jwt('returns', 'write')
@audit_decorator('returns', 'CREATE')
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
        
        # Validate return quantity
        is_valid, error_msg = ReturnService.validate_return_quantity(
            data['invoice_id'], data['product_id'], quantity
        )
        if not is_valid:
            return jsonify({"error": error_msg}), 400
        
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
@require_permission_jwt('returns', 'read')
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
@require_permission_jwt('returns', 'read')
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
@require_permission_jwt('returns', 'read')
def get_damaged_products():
    """Get inventory of damaged products"""
    try:
        inventory = ReturnService.get_damaged_products_inventory()
        return jsonify(inventory), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@return_bp.route('/damaged-products/<int:id>', methods=['GET'])
@require_permission_jwt('returns', 'read')
def get_damaged_product_by_id(id):
    """Get specific damaged product by ID with all details"""
    try:
        damaged_product = DamagedProduct.query.get_or_404(id)
        
        # Get return details
        return_record = damaged_product.return_record if damaged_product.return_record else None
        
        # Get customer details
        customer = None
        if return_record and return_record.customer:
            customer = return_record.customer
        
        # Get invoice details
        invoice = None
        if return_record and return_record.original_invoice:
            invoice = return_record.original_invoice
        
        # Get product details with category
        product = damaged_product.product
        category = None
        if product and product.category_id:
            from category.category import Category
            category = Category.query.get(product.category_id)
        
        # Get payment details if invoice exists
        payment_details = None
        if invoice:
            from payments.payment import Payment
            payments = Payment.query.filter_by(invoice_id=invoice.id).all()
            total_paid = sum([float(p.amount_paid) for p in payments])
            payment_details = {
                "total_invoice_amount": float(invoice.grand_total),
                "total_paid": total_paid,
                "pending_amount": float(invoice.grand_total) - total_paid,
                "payment_status": "Paid" if total_paid >= float(invoice.grand_total) else "Pending"
            }
        
        # Calculate damage value
        damage_value = float(return_record.original_price) * damaged_product.quantity if return_record else 0
        
        return jsonify({
            "damaged_product_id": damaged_product.id,
            "return_id": damaged_product.return_id,
            "return_number": return_record.return_number if return_record else None,
            "quantity_damaged": damaged_product.quantity,
            "damage_level": damaged_product.damage_level,
            "damage_reason": damaged_product.damage_reason,
            "damage_date": damaged_product.damage_date.strftime("%Y-%m-%d %H:%M:%S"),
            "storage_location": damaged_product.storage_location,
            "status": damaged_product.status,
            "action_taken": damaged_product.action_taken,
            "action_date": damaged_product.action_date.strftime("%Y-%m-%d %H:%M:%S") if damaged_product.action_date else None,
            "repair_cost": float(damaged_product.repair_cost) if damaged_product.repair_cost else 0,
            "damage_value": damage_value,
            "customer_details": {
                "customer_id": customer.id if customer else None,
                "customer_name": customer.contact_person if customer else None,
                "business_name": customer.business_name if customer else None,
                "phone": customer.phone if customer else None,
                "email": customer.email if customer else None,
                "address": customer.billing_address if customer else None
            } if customer else None,
            "product_details": {
                "product_id": product.id if product else None,
                "product_name": product.product_name if product else None,
                "sku": product.sku if product else None,
                "original_price": float(return_record.original_price) if return_record else 0,
                "current_stock": product.quantity_in_stock if product else 0,
                "category_name": category.name if category else None
            } if product else None,
            "invoice_details": {
                "invoice_id": invoice.id if invoice else None,
                "invoice_number": invoice.invoice_number if invoice else None,
                "invoice_date": invoice.invoice_date.strftime("%Y-%m-%d") if invoice else None,
                "grand_total": float(invoice.grand_total) if invoice else 0,
                "payment_terms": invoice.payment_terms if invoice else None
            } if invoice else None,
            "payment_details": payment_details,
            "refund_details": {
                "refund_amount": float(return_record.refund_amount) if return_record and return_record.refund_amount else 0,
                "refund_status": return_record.status if return_record else None,
                "return_date": return_record.return_date.strftime("%Y-%m-%d %H:%M:%S") if return_record else None,
                "return_type": return_record.return_type if return_record else None,
                "product_type": return_record.product_type if return_record else None
            } if return_record else None,
            "created_at": damaged_product.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at": damaged_product.updated_at.strftime("%Y-%m-%d %H:%M:%S") if damaged_product.updated_at else None
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@return_bp.route('/damaged-products/', methods=['POST'])
@require_permission_jwt('returns', 'write')
@audit_decorator('returns', 'DAMAGE')
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
        
        # Validate return quantity
        is_valid, error_msg = ReturnService.validate_return_quantity(
            data['invoice_id'], data['product_id'], quantity
        )
        if not is_valid:
            return jsonify({"error": error_msg}), 400
        
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
@require_permission_jwt('returns', 'read')
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
@require_permission_jwt('returns', 'write')
@audit_decorator('returns', 'ADJUSTMENT')
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
        
        # Validate return quantity
        is_valid, error_msg = ReturnService.validate_return_quantity(
            data['invoice_id'], data['product_id'], quantity
        )
        if not is_valid:
            return jsonify({"error": error_msg}), 400
        
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
        return jsonify({"error": str(e)}), 500


@return_bp.route('/returns/export', methods=['GET'])
@require_permission_jwt('returns', 'read')
def export_returns_data():
    try:
        format_type = request.args.get('format', 'csv').lower()
        export_type = request.args.get('type', 'all')  # all, returns, adjustments, damage
        
        data = []
        
        if export_type in ['all', 'returns']:
            # Get regular returns
            returns = ProductReturn.query.filter_by(return_type='return').all()
            for r in returns:
                data.append({
                    "Type": "Return",
                    "ID": r.id,
                    "Return Number": r.return_number,
                    "Customer ID": r.customer_id,
                    "Customer Name": r.customer.contact_person if r.customer else '',
                    "Product ID": r.product_id,
                    "Product Name": r.product.product_name if r.product else '',
                    "Quantity": r.quantity_returned,
                    "Original Price": float(r.original_price or 0),
                    "Refund Amount": float(r.refund_amount or 0),
                    "Status": r.status,
                    "Date": r.return_date.strftime('%Y-%m-%d %H:%M:%S'),
                    "Reason": r.reason or '',
                    "Notes": r.notes or '',
                    "Exchange Product ID": '',
                    "Exchange Product Name": '',
                    "Exchange Quantity": '',
                    "Price Difference": '',
                    "Damage Level": '',
                    "Is Resaleable": ''
                })
        
        if export_type in ['all', 'adjustments']:
            # Get adjustments (exchanges)
            adjustments = ProductReturn.query.filter_by(return_type='exchange').all()
            for adj in adjustments:
                data.append({
                    "Type": "Adjustment/Exchange",
                    "ID": adj.id,
                    "Return Number": adj.return_number,
                    "Customer ID": adj.customer_id,
                    "Customer Name": adj.customer.contact_person if adj.customer else '',
                    "Product ID": adj.product_id,
                    "Product Name": adj.product.product_name if adj.product else '',
                    "Quantity": adj.quantity_returned,
                    "Original Price": float(adj.original_price or 0),
                    "Refund Amount": float(adj.refund_amount or 0),
                    "Status": adj.status,
                    "Date": adj.return_date.strftime('%Y-%m-%d %H:%M:%S'),
                    "Reason": adj.reason or '',
                    "Notes": adj.notes or '',
                    "Exchange Product ID": adj.exchange_product_id or '',
                    "Exchange Product Name": adj.exchange_product.product_name if adj.exchange_product else '',
                    "Exchange Quantity": adj.exchange_quantity or '',
                    "Price Difference": float(adj.exchange_price_difference or 0),
                    "Damage Level": '',
                    "Is Resaleable": ''
                })
        
        if export_type in ['all', 'damage']:
            # Get damage returns
            damage_returns = ProductReturn.query.filter_by(return_type='damage').all()
            for dmg in damage_returns:
                data.append({
                    "Type": "Damage",
                    "ID": dmg.id,
                    "Return Number": dmg.return_number,
                    "Customer ID": dmg.customer_id,
                    "Customer Name": dmg.customer.contact_person if dmg.customer else '',
                    "Product ID": dmg.product_id,
                    "Product Name": dmg.product.product_name if dmg.product else '',
                    "Quantity": dmg.quantity_returned,
                    "Original Price": float(dmg.original_price or 0),
                    "Refund Amount": float(dmg.refund_amount or 0),
                    "Status": dmg.status,
                    "Date": dmg.return_date.strftime('%Y-%m-%d %H:%M:%S'),
                    "Reason": dmg.reason or '',
                    "Notes": dmg.notes or '',
                    "Exchange Product ID": '',
                    "Exchange Product Name": '',
                    "Exchange Quantity": '',
                    "Price Difference": '',
                    "Damage Level": dmg.damage_level or '',
                    "Is Resaleable": str(dmg.is_resaleable) if dmg.is_resaleable is not None else ''
                })
            
            # Get damaged products inventory
            damaged_products = DamagedProduct.query.all()
            for dp in damaged_products:
                product = Product.query.get(dp.product_id) if dp.product_id else None
                data.append({
                    "Type": "Damaged Stock",
                    "ID": dp.id,
                    "Return Number": '',
                    "Customer ID": '',
                    "Customer Name": '',
                    "Product ID": dp.product_id,
                    "Product Name": product.product_name if product else '',
                    "Quantity": dp.quantity,
                    "Original Price": '',
                    "Refund Amount": '',
                    "Status": dp.status,
                    "Date": dp.damage_date.strftime('%Y-%m-%d %H:%M:%S'),
                    "Reason": dp.damage_reason or '',
                    "Notes": '',
                    "Exchange Product ID": '',
                    "Exchange Product Name": '',
                    "Exchange Quantity": '',
                    "Price Difference": '',
                    "Damage Level": dp.damage_level or '',
                    "Is Resaleable": ''
                })
        
        df = pd.DataFrame(data)
        
        if format_type == 'excel':
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Returns & Adjustments', index=False)
            output.seek(0)
            
            return send_file(
                output,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name=f'returns_adjustments_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
            )
        else:
            output = io.StringIO()
            df.to_csv(output, index=False)
            response = make_response(output.getvalue())
            response.headers['Content-Type'] = 'text/csv; charset=utf-8'
            response.headers['Content-Disposition'] = f'attachment; filename=returns_adjustments_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
            return response
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500
@return_bp.route('/returns/<int:return_id>', methods=['DELETE'])
@require_permission_jwt('returns', 'write')
@audit_decorator('returns', 'DELETE')
def delete_return(return_id):
    return_item = ProductReturn.query.get(return_id)
    if not return_item:
        return jsonify({"error": "Return not found"}), 404
    
    try:
        db.session.delete(return_item)
        db.session.commit()
        return jsonify({"message": "Return deleted successfully"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400

@return_bp.route('/damaged-products/<int:damaged_id>', methods=['DELETE'])
@require_permission_jwt('returns', 'write')
@audit_decorator('returns', 'DELETE_DAMAGED')
def delete_damaged_product(damaged_id):
    damaged_product = DamagedProduct.query.get(damaged_id)
    if not damaged_product:
        return jsonify({"error": "Damaged product not found"}), 404
    
    try:
        db.session.delete(damaged_product)
        db.session.commit()
        return jsonify({"message": "Damaged product deleted successfully"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400