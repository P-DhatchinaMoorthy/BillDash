from flask import Blueprint, request, jsonify
from datetime import datetime, date
from src.extensions import db
from reports.report import Report
from reports.report_service import ReportService
from products.product import Product
from invoices.invoice import Invoice
from customers.customer import Customer
from payments.payment import Payment
from sales_no_invoice.sale_no_invoice import SaleNoInvoice
from user.enhanced_auth_middleware import require_permission_jwt
from sqlalchemy import func, desc

bp = Blueprint("reports", __name__)

@bp.route("/sales", methods=["GET"])
@require_permission_jwt('reports', 'read')
def get_sales_report():
    try:
        report_data = ReportService.generate_sales_report()
        return jsonify(report_data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route("/stock", methods=["GET"])
@require_permission_jwt('reports', 'read')
def get_stock_report():
    try:
        report_data = ReportService.generate_stock_report()
        return jsonify(report_data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route("/profit-loss", methods=["GET"])
@require_permission_jwt('reports', 'read')
def get_profit_loss_report():
    try:
        # Get date parameters from query string
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        if start_date:
            start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
        if end_date:
            end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
            
        report_data = ReportService.generate_profit_loss_report(start_date, end_date)
        return jsonify(report_data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route("/dashboard-test", methods=["GET"])
@require_permission_jwt('reports', 'read')
def get_dashboard_test():
    try:
        # Simple test to check if data exists
        products_count = Product.query.count()
        customers_count = Customer.query.count()
        invoices_count = Invoice.query.count()
        
        return jsonify({
            "test_results": {
                "products_count": products_count,
                "customers_count": customers_count,
                "invoices_count": invoices_count,
                "status": "working"
            }
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/dashboard", methods=["GET"])
@require_permission_jwt('reports', 'read')
def get_dashboard_report():
    products_count = Product.query.count()
    customers_count = Customer.query.count()
    invoices_count = Invoice.query.count()
    
    total_sales = float(db.session.query(func.coalesce(func.sum(Invoice.grand_total), 0)).scalar())
    
    products = Product.query.all()
    stock_value = sum([p.quantity_in_stock * float(p.purchase_price or 0) for p in products])
    
    from stock_transactions.stock_transaction import StockTransaction
    import json
    purchase_transactions = StockTransaction.query.filter_by(transaction_type="Purchase").all()
    total_purchases = 0
    for pt in purchase_transactions:
        if pt.notes:
            try:
                payment_info = json.loads(pt.notes)
                total_purchases += float(payment_info.get("total_amount", 0))
            except:
                pass
    
    net_amount = total_sales - total_purchases
    profit_loss_status = "Profit" if net_amount >= 0 else "Loss"
    
    return jsonify({
        "dashboard_summary": {
            "report_id": f"DASH-{datetime.now().strftime('%Y-%m-%d')}",
            "generated_date": datetime.now().isoformat(),
            "period": "Current Month"
        },
        "key_metrics": {
            "total_sales": f"{total_sales:.2f}",
            "total_purchases": f"{total_purchases:.2f}",
            "net_profit": f"{abs(net_amount):.2f}",
            "profit_loss_status": profit_loss_status,
            "stock_value": f"{stock_value:.2f}"
        },
        "quick_stats": {
            "active_customers": customers_count,
            "total_products": products_count,
            "pending_payments": "0.00",
            "low_stock_alerts": len([p for p in products if p.reorder_level and p.quantity_in_stock <= p.reorder_level])
        },
        "recent_activity": [],
        "charts_data": {
            "monthly_sales": [0, 0, 0, f"{total_sales:.2f}"] if total_sales > 0 else [0, 0, 0, 0],
            "payment_methods": {"cash": max(1, Payment.query.count())}
        }
    }), 200

@bp.route("/", methods=["GET"])
@require_permission_jwt('reports', 'read')
def list_reports():
    try:
        total_products = Product.query.count()
    except:
        total_products = 0
    
    try:
        sales = SaleNoInvoice.query.all()
        total_sales = sum([float(s.total_amount) for s in sales if hasattr(s, 'total_amount')])
    except:
        total_sales = 0
    
    return jsonify([
        {
            "id": 1,
            "report_name": "Sales Report",
            "generated_by": "Admin",
            "date_range": "Current Month",
            "total_sales": str(total_sales),
            "generated_date": datetime.now().isoformat()
        },
        {
            "id": 2,
            "report_name": "Stock Report", 
            "generated_by": "Admin",
            "date_range": "Current",
            "total_products": str(total_products),
            "generated_date": datetime.now().isoformat()
        }
    ]), 200

@bp.route("/sales-no-invoice", methods=["GET"])
@require_permission_jwt('reports', 'read')
def get_sales_no_invoice_report():
    try:
        sales = SaleNoInvoice.query.all()
        
        sales_data = []
        total_amount = 0
        for sale in sales:
            sales_data.append({
                "id": sale.id,
                "product_name": sale.product.product_name if sale.product else "Unknown",
                "quantity": sale.quantity,
                "selling_price": float(sale.selling_price),
                "total_amount": float(sale.total_amount),
                "payment_method": sale.payment_method,
                "sale_date": sale.sale_date.strftime("%Y-%m-%d %H:%M:%S")
            })
            total_amount += float(sale.total_amount)
        
        return jsonify({
            "report_name": "Sales Without Invoice Report",
            "total_sales": total_amount,
            "total_transactions": len(sales),
            "sales": sales_data
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route("/invoices", methods=["GET"])
@require_permission_jwt('reports', 'read')
def get_invoices_report():
    try:
        invoices = Invoice.query.all()
        
        # Status-wise breakdown
        status_summary = {"Paid": {"count": 0, "amount": 0}, "Pending": {"count": 0, "amount": 0}, "Partially Paid": {"count": 0, "amount": 0}}
        
        invoices_data = []
        total_amount = 0
        total_paid = 0
        total_pending = 0
        
        for invoice in invoices:
            # Get payment details
            payments = Payment.query.filter_by(invoice_id=invoice.id).all()
            paid_amount = sum([float(p.amount_paid) for p in payments])
            pending_amount = float(invoice.grand_total) - paid_amount
            
            # Determine status
            if paid_amount >= float(invoice.grand_total):
                status = "Paid"
            elif paid_amount > 0:
                status = "Partially Paid"
            else:
                status = "Pending"
            
            # Update status summary
            if status in status_summary:
                status_summary[status]["count"] += 1
                status_summary[status]["amount"] += float(invoice.grand_total)
            
            invoices_data.append({
                "id": invoice.id,
                "invoice_number": invoice.invoice_number,
                "customer_name": invoice.customer.contact_person if invoice.customer else "Unknown",
                "grand_total": f"{float(invoice.grand_total):.2f}",
                "paid_amount": f"{paid_amount:.2f}",
                "pending_amount": f"{pending_amount:.2f}",
                "status": status,
                "invoice_date": invoice.invoice_date.strftime("%Y-%m-%d")
            })
            
            total_amount += float(invoice.grand_total)
            total_paid += paid_amount
            total_pending += pending_amount
        
        # Check if user wants detailed list
        show_details = request.args.get('details', 'false').lower() == 'true'
        
        response = {
            "report_name": "Invoice Report",
            "report_summary": {
                "total_invoices": len(invoices),
                "total_amount": f"{total_amount:.2f}",
                "total_paid_amount": f"{total_paid:.2f}",
                "total_pending_amount": f"{total_pending:.2f}"
            },
            "status_breakdown": {
                "paid_invoices": {"count": status_summary["Paid"]["count"], "amount": f"{status_summary['Paid']['amount']:.2f}"},
                "pending_invoices": {"count": status_summary["Pending"]["count"], "amount": f"{status_summary['Pending']['amount']:.2f}"},
                "partially_paid_invoices": {"count": status_summary["Partially Paid"]["count"], "amount": f"{status_summary['Partially Paid']['amount']:.2f}"}
            }
        }
        
        if show_details:
            response["invoices"] = invoices_data
            
        return jsonify(response), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route("/purchases", methods=["GET"])
@require_permission_jwt('reports', 'read')
def get_purchases_report():
    try:
        from models.purchase_bill import PurchaseBill
        purchases = PurchaseBill.query.all()
        
        purchases_data = []
        total_amount = 0
        for purchase in purchases:
            purchases_data.append({
                "id": purchase.id,
                "bill_number": purchase.bill_number,
                "supplier_name": purchase.supplier.company_name if purchase.supplier else "Unknown",
                "total_amount": float(purchase.total_amount),
                "payment_status": purchase.payment_status,
                "bill_date": purchase.bill_date.strftime("%Y-%m-%d %H:%M:%S")
            })
            total_amount += float(purchase.total_amount)
        
        return jsonify({
            "report_name": "Purchase Report",
            "total_purchases_amount": total_amount,
            "total_purchases": len(purchases),
            "purchases": purchases_data
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route("/stock-movement", methods=["GET"])
@require_permission_jwt('reports', 'read')
def get_stock_movement_report():
    try:
        location = request.args.get('location')
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        
        from stock_transactions.stock_transaction import StockTransaction
        from products.product import Product
        from invoices.invoice_item import InvoiceItem
        from customers.customer import Customer
        from suppliers.supplier import Supplier
        from datetime import datetime
        from sqlalchemy import func, desc
        
        # Get date range
        if date_from:
            date_from_obj = datetime.strptime(date_from, "%Y-%m-%d")
        else:
            date_from_obj = datetime.now().replace(day=1)  # Start of current month
            
        if date_to:
            date_to_obj = datetime.strptime(date_to, "%Y-%m-%d")
        else:
            date_to_obj = datetime.now()
        
        # Get frequently sold products (top 10)
        frequently_sold = db.session.query(
            InvoiceItem.product_id,
            func.sum(InvoiceItem.quantity).label('total_sold')
        ).group_by(InvoiceItem.product_id).order_by(desc('total_sold')).limit(10).all()
        
        frequently_sold_ids = [item.product_id for item in frequently_sold]
        
        # Get stock transactions for the period
        query = StockTransaction.query.filter(
            StockTransaction.transaction_date >= date_from_obj,
            StockTransaction.transaction_date <= date_to_obj
        )
        
        transactions = query.order_by(StockTransaction.transaction_date.desc()).all()
        
        stock_movements = []
        filtered_transactions = []
        
        for t in transactions:
            product = Product.query.get(t.product_id)
            supplier = Supplier.query.get(t.supplier_id) if t.supplier_id else None
            
            # Get customer info from invoice if available
            customer = None
            customer_location = None
            if t.invoice_id:
                invoice = Invoice.query.get(t.invoice_id)
                if invoice and invoice.customer_id:
                    customer = Customer.query.get(invoice.customer_id)
                    customer_location = customer.branch if customer and customer.branch else None
            
            # Apply location filter - Fixed logic
            if location:
                # If location filter is specified, only include transactions that match
                if customer_location:
                    # Case-insensitive exact match or contains match
                    if location.lower() != customer_location.lower() and location.lower() not in customer_location.lower():
                        continue
                else:
                    # Skip transactions without customer location when location filter is applied
                    continue
            
            # Add to filtered transactions for summary calculation
            filtered_transactions.append(t)
            
            is_frequent = t.product_id in frequently_sold_ids
            
            stock_movements.append({
                "transaction_id": t.id,
                "product_id": t.product_id,
                "product_name": product.product_name if product else None,
                "sku": product.sku if product else None,
                "transaction_type": t.transaction_type,
                "quantity": t.quantity,
                "transaction_date": t.transaction_date.isoformat(),
                "reference_number": t.reference_number,
                "location": customer_location,
                "customer_name": customer.contact_person if customer else None,
                "supplier_name": supplier.name if supplier else None,
                "current_stock": product.quantity_in_stock if product else None,
                "is_frequently_sold": is_frequent
            })
        
        # Summary statistics based on filtered transactions
        total_in = sum(t.quantity for t in filtered_transactions if t.transaction_type == 'Purchase')
        total_out = sum(t.quantity for t in filtered_transactions if t.transaction_type == 'Sale')
        
        # Get available locations for reference
        available_locations = []
        customers_with_locations = Customer.query.filter(Customer.branch.isnot(None)).all()
        for customer in customers_with_locations:
            if customer.branch and customer.branch not in available_locations:
                available_locations.append(customer.branch)
        
        return jsonify({
            "report_name": "Stock Movement Report",
            "date_range": {
                "from": date_from_obj.strftime("%Y-%m-%d"),
                "to": date_to_obj.strftime("%Y-%m-%d")
            },
            "location_filter": location,
            "available_locations": sorted(available_locations),
            "summary": {
                "total_transactions": len(filtered_transactions),
                "total_stock_in": total_in,
                "total_stock_out": total_out,
                "net_movement": total_in - total_out,
                "filtered_by_location": bool(location)
            },
            "frequently_sold_products": [
                {
                    "product_id": item.product_id,
                    "product_name": Product.query.get(item.product_id).product_name,
                    "total_sold": int(item.total_sold)
                } for item in frequently_sold
            ],
            "stock_movements": stock_movements
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/reorder", methods=["GET"])
@require_permission_jwt('reports', 'read')
def get_reorder_report():
    try:
        from category.category import Category
        from suppliers.supplier import Supplier
        
        # Get products that need reordering
        products = Product.query.filter(
            Product.reorder_level.isnot(None),
            Product.quantity_in_stock <= Product.reorder_level
        ).all()
        
        reorder_items = []
        total_reorder_value = 0
        
        for product in products:
            category = Category.query.get(product.category_id) if product.category_id else None
            supplier = Supplier.query.get(product.supplier_id) if product.supplier_id else None
            
            shortage = product.reorder_level - product.quantity_in_stock
            suggested_order_qty = max(shortage, product.reorder_level)
            order_value = suggested_order_qty * float(product.purchase_price or 0)
            
            reorder_items.append({
                "product_id": product.id,
                "product_name": product.product_name,
                "sku": product.sku,
                "category_name": category.name if category else None,
                "supplier_name": supplier.name if supplier else None,
                "current_stock": product.quantity_in_stock,
                "reorder_level": product.reorder_level,
                "shortage": shortage,
                "suggested_order_qty": suggested_order_qty,
                "purchase_price": float(product.purchase_price or 0),
                "order_value": order_value,
                "unit_of_measure": product.unit_of_measure
            })
            total_reorder_value += order_value
        
        return jsonify({
            "report_name": "Reorder Report",
            "generated_date": datetime.now().isoformat(),
            "summary": {
                "total_items_to_reorder": len(reorder_items),
                "total_reorder_value": round(total_reorder_value, 2)
            },
            "reorder_items": sorted(reorder_items, key=lambda x: x['shortage'], reverse=True)
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route("/debug/locations", methods=["GET"])
@require_permission_jwt('reports', 'read')
def debug_locations():
    """Debug endpoint to check available customer locations"""
    try:
        from customers.customer import Customer
        from stock_transactions.stock_transaction import StockTransaction
        from invoices.invoice import Invoice
        
        # Get all customers with locations
        customers = Customer.query.filter(Customer.branch.isnot(None)).all()
        customer_locations = []
        for customer in customers:
            customer_locations.append({
                "customer_id": customer.id,
                "contact_person": customer.contact_person,
                "branch": customer.branch
            })
        
        # Get unique locations
        unique_locations = list(set([c.branch for c in customers if c.branch]))
        
        # Get stock transactions with customer info
        transactions_with_customers = []
        transactions = StockTransaction.query.limit(10).all()
        for t in transactions:
            if t.invoice_id:
                invoice = Invoice.query.get(t.invoice_id)
                if invoice and invoice.customer_id:
                    customer = Customer.query.get(invoice.customer_id)
                    transactions_with_customers.append({
                        "transaction_id": t.id,
                        "customer_name": customer.contact_person if customer else None,
                        "customer_location": customer.branch if customer else None,
                        "transaction_type": t.transaction_type
                    })
        
        return jsonify({
            "total_customers": Customer.query.count(),
            "customers_with_locations": len(customer_locations),
            "unique_locations": unique_locations,
            "customer_locations": customer_locations,
            "sample_transactions_with_customers": transactions_with_customers,
            "total_stock_transactions": StockTransaction.query.count()
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route("/generate", methods=["POST"])
@require_permission_jwt('reports', 'write')
def generate_report():
    data = request.get_json() or {}
    report_type = data.get("report_type")
    start_date = data.get("start_date")
    end_date = data.get("end_date")
    
    if not all([report_type, start_date, end_date]):
        return jsonify({"error": "report_type, start_date, end_date required"}), 400
    
    try:
        if report_type == "sales":
            report_data = ReportService.generate_sales_report()
        elif report_type == "stock":
            report_data = ReportService.generate_stock_report()
        else:
            return jsonify({"error": "Invalid report_type. Use 'sales' or 'stock'"}), 400
        
        return jsonify({
            "report_id": f"RPT-{datetime.now().strftime('%Y%m%d%H%M')}",
            "message": f"{report_type.title()} report generated successfully",
            "data": report_data
        }), 201
        
    except Exception as e:
        return jsonify({"error": str(e)}), 400
@bp.route("/<int:report_id>", methods=["DELETE"])
@require_permission_jwt('reports', 'write')
def delete_report(report_id):
    r = Report.query.get(report_id)
    if not r:
        return jsonify({"error": "Report not found"}), 404
    
    try:
        db.session.delete(r)
        db.session.commit()
        return jsonify({"message": "Report deleted successfully"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400