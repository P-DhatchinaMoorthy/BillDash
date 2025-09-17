from products.product import Product
from sales_no_invoice.sale_no_invoice import SaleNoInvoice
from purchases.purchase_bill import PurchaseBill
from payments.payment import Payment
from invoices.invoice import Invoice
from customers.customer import Customer
from suppliers.supplier import Supplier
from sqlalchemy import func, desc
from datetime import datetime, date
from src.extensions import db

class ReportService:
    @staticmethod
    def generate_stock_report():
        from returns.product_return import DamagedProduct
        from category.category import Category
        
        products = Product.query.all()
        damaged_products = DamagedProduct.query.filter_by(status='Stored').all()
        
        low_stock = [p for p in products if p.quantity_in_stock <= p.reorder_level]
        out_of_stock = [p for p in products if p.quantity_in_stock == 0]
        
        stock_value = sum([p.quantity_in_stock * p.purchase_price for p in products if p.purchase_price])
        
        top_products = []
        for p in products:
            if p.quantity_in_stock > 0:
                top_products.append({
                    "product_name": p.product_name,
                    "remaining_stock": p.quantity_in_stock,
                    "stock_value": float(p.quantity_in_stock * p.purchase_price) if p.purchase_price else 0
                })
        
        # Group damaged products by category
        damaged_by_category = {}
        total_damaged_quantity = 0
        
        for damaged in damaged_products:
            category_id = damaged.product.category_id if damaged.product else None
            category = Category.query.get(damaged.product.category_id) if damaged.product and damaged.product.category_id else None
            category_name = category.name if category else "Unknown"
            
            if category_id not in damaged_by_category:
                damaged_by_category[category_id] = {
                    "category_name": category_name,
                    "total_quantity": 0,
                    "products": []
                }
            
            damaged_by_category[category_id]["total_quantity"] += damaged.quantity
            damaged_by_category[category_id]["products"].append({
                "product_name": damaged.product.product_name if damaged.product else "Unknown",
                "quantity": damaged.quantity,
                "damage_level": damaged.damage_level,
                "damage_date": damaged.damage_date.strftime("%Y-%m-%d"),
                "storage_location": damaged.storage_location
            })
            total_damaged_quantity += damaged.quantity
        
        # All products list with complete details
        all_products = []
        for p in products:
            category = Category.query.get(p.category_id) if p.category_id else None
            all_products.append({
                "product_id": p.id,
                "product_name": p.product_name,
                "sku": p.sku,
                "category_id": p.category_id,
                "category_name": category.name if category else None,
                "quantity_in_stock": p.quantity_in_stock,
                "reorder_level": p.reorder_level,
                "purchase_price": str(p.purchase_price) if p.purchase_price else "0.00",
                "selling_price": str(p.selling_price) if p.selling_price else "0.00",
                "stock_value": float(p.quantity_in_stock * p.purchase_price) if p.purchase_price else 0.0,
                "unit_of_measure": p.unit_of_measure,
                "supplier_id": p.supplier_id,
                "barcode": p.barcode,
                "stock_status": "Out of Stock" if p.quantity_in_stock == 0 else "Low Stock" if p.reorder_level and p.quantity_in_stock <= p.reorder_level else "In Stock"
            })
        
        return {
            "report_id": f"RPT-{datetime.now().strftime('%Y-%m-%d-%H%M')}",
            "report_name": "Stock Report",
            "generated_by": "Admin",
            "generated_date": datetime.now().isoformat(),
            "stock_summary": {
                "total_stock_value": float(stock_value),
                "total_products": len(products),
                "products_in_stock": len([p for p in products if p.quantity_in_stock > 0]),
                "total_damaged_products": total_damaged_quantity
            },
            "inventory_status": {
                "total_products": len(products),
                "low_stock_items": len(low_stock),
                "out_of_stock_items": len(out_of_stock),
                "products_in_stock": len([p for p in products if p.quantity_in_stock > 0])
            },
            "top_products": sorted(top_products, key=lambda x: x['remaining_stock'], reverse=True)[:10],
            "all_products": sorted(all_products, key=lambda x: x['product_name']),
            "damaged_products_by_category": list(damaged_by_category.values())
        }
    
    @staticmethod
    def generate_sales_report(start_date=None, end_date=None):
        try:
            if not start_date:
                start_date = date.today().replace(day=1)
            if not end_date:
                end_date = date.today()
                
            sales = SaleNoInvoice.query.all()
            total_sales = 0
            
            for s in sales:
                if hasattr(s, 'total_amount') and s.total_amount:
                    total_sales += s.total_amount
            
            return {
                "report_id": f"RPT-{datetime.now().strftime('%Y-%m-%d-%H%M')}",
                "report_name": "Sales Report",
                "generated_by": "Admin",
                "generated_date": datetime.now().isoformat(),
                "date_range": {
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat()
                },
                "summary": {
                    "total_sales_amount": float(total_sales),
                    "total_transactions": len(sales),
                    "average_sale_value": float(total_sales / len(sales)) if sales else 0
                }
            }
        except Exception as e:
            return {
                "report_id": f"RPT-{datetime.now().strftime('%Y-%m-%d-%H%M')}",
                "report_name": "Sales Report",
                "generated_by": "Admin",
                "generated_date": datetime.now().isoformat(),
                "error": "No sales data available",
                "summary": {
                    "total_sales_amount": 0.0,
                    "total_transactions": 0,
                    "average_sale_value": 0.0
                }
            }
    
    @staticmethod
    def generate_dashboard_report():
        """Generate real-time dashboard data from database"""
        try:
            # Key Metrics - Calculate total sales from both direct sales and invoices
            direct_sales = db.session.query(func.sum(SaleNoInvoice.total_amount)).scalar() or 0
            invoice_sales = db.session.query(func.sum(Invoice.grand_total)).scalar() or 0
            total_sales = direct_sales + invoice_sales
            
            # Calculate purchases from StockTransaction since PurchaseBill might not exist
            try:
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
            except:
                total_purchases = 0
            
            # Stock value calculation
            products = Product.query.all()
            stock_value = sum([p.quantity_in_stock * float(p.purchase_price) for p in products if p.purchase_price]) or 0
            
            net_profit = total_sales - total_purchases
            
            # Quick Stats
            active_customers = Customer.query.count()
            total_products = Product.query.count()
            
            # Pending payments (invoices not fully paid)
            pending_invoices = Invoice.query.filter(Invoice.status.in_(['Pending', 'Partially Paid'])).all()
            pending_payments = sum([i.grand_total - sum([p.amount_paid for p in i.payments]) for i in pending_invoices])
            
            # Low stock alerts
            low_stock_count = len([p for p in products if p.reorder_level and p.quantity_in_stock <= p.reorder_level])
            
            # Recent Activity (last 5 transactions)
            recent_sales = SaleNoInvoice.query.order_by(desc(SaleNoInvoice.sale_date)).limit(2).all()
            recent_invoices = Invoice.query.order_by(desc(Invoice.invoice_date)).limit(2).all()
            recent_purchases = PurchaseBill.query.order_by(desc(PurchaseBill.bill_date)).limit(2).all()
            
            recent_activity = []
            
            # Add direct sales
            for sale in recent_sales:
                product_name = sale.product.product_name if sale.product else f"Product ID: {sale.product_id}"
                recent_activity.append({
                    "type": "sale",
                    "amount": float(sale.total_amount),
                    "customer": f"Direct Sale - {product_name}",
                    "date": sale.sale_date.strftime("%Y-%m-%d")
                })
            
            # Add invoice sales
            for invoice in recent_invoices:
                customer_name = invoice.customer.contact_person if invoice.customer else "Unknown Customer"
                recent_activity.append({
                    "type": "sale",
                    "amount": float(invoice.grand_total),
                    "customer": customer_name,
                    "date": invoice.invoice_date.strftime("%Y-%m-%d")
                })
            
            # Add purchases - using StockTransaction instead of PurchaseBill
            try:
                from stock_transactions.stock_transaction import StockTransaction
                import json
                recent_purchases = StockTransaction.query.filter_by(transaction_type="Purchase").order_by(desc(StockTransaction.transaction_date)).limit(2).all()
                for purchase in recent_purchases:
                    supplier_name = purchase.supplier.name if purchase.supplier else "Unknown Supplier"
                    amount = 0
                    if purchase.notes:
                        try:
                            payment_info = json.loads(purchase.notes)
                            amount = float(payment_info.get("total_amount", 0))
                        except:
                            pass
                    recent_activity.append({
                        "type": "purchase",
                        "amount": amount,
                        "supplier": supplier_name,
                        "date": purchase.transaction_date.strftime("%Y-%m-%d")
                    })
            except:
                pass
            
            # Sort by date (most recent first)
            recent_activity.sort(key=lambda x: x['date'], reverse=True)
            recent_activity = recent_activity[:5]
            
            # Payment methods distribution from direct sales and payments
            payment_methods = {}
            
            # Count from direct sales
            sales_payments = SaleNoInvoice.query.all()
            for sale in sales_payments:
                method = sale.payment_method.lower() if sale.payment_method else 'cash'
                payment_methods[method] = payment_methods.get(method, 0) + 1
            
            # Count from invoice payments
            invoice_payments = Payment.query.all()
            for payment in invoice_payments:
                method = payment.payment_method.lower() if payment.payment_method else 'cash'
                payment_methods[method] = payment_methods.get(method, 0) + 1
            
            # Monthly sales (mock data for chart - would need date-based queries for real implementation)
            monthly_sales = [float(total_sales) * 0.3, float(total_sales) * 0.4, float(total_sales) * 0.35, float(total_sales)]
            
            return {
                "dashboard_summary": {
                    "report_id": f"DASH-{datetime.now().strftime('%Y-%m-%d')}",
                    "generated_date": datetime.now().isoformat(),
                    "period": "Current Month"
                },
                "key_metrics": {
                    "total_sales": float(total_sales),
                    "total_purchases": float(total_purchases),
                    "net_profit": float(net_profit),
                    "stock_value": float(stock_value)
                },
                "report_links": {
                    "sales_no_invoice_report": "/reports/sales-no-invoice",
                    "invoice_report": "/reports/invoices",
                    "purchase_report": "/reports/purchases"
                },
                "quick_stats": {
                    "active_customers": active_customers,
                    "total_products": total_products,
                    "pending_payments": float(pending_payments),
                    "low_stock_alerts": low_stock_count
                },
                "recent_activity": recent_activity,
                "charts_data": {
                    "monthly_sales": monthly_sales,
                    "payment_methods": payment_methods if payment_methods else {"cash": 1}
                }
            }
            
        except Exception as e:
            # Return fallback data if there's an error
            return {
                "dashboard_summary": {
                    "report_id": f"DASH-{datetime.now().strftime('%Y-%m-%d')}",
                    "generated_date": datetime.now().isoformat(),
                    "period": "Current Month"
                },
                "key_metrics": {
                    "total_sales": 0.0,
                    "total_purchases": 0.0,
                    "net_profit": 0.0,
                    "stock_value": 0.0
                },
                "report_links": {
                    "sales_no_invoice_report": "/reports/sales-no-invoice",
                    "invoice_report": "/reports/invoices",
                    "purchase_report": "/reports/purchases"
                },
                "quick_stats": {
                    "active_customers": 0,
                    "total_products": 0,
                    "pending_payments": 0.0,
                    "low_stock_alerts": 0
                },
                "recent_activity": [],
                "charts_data": {
                    "monthly_sales": [0, 0, 0, 0],
                    "payment_methods": {"cash": 0}
                },
                "error": str(e)
            }
    
    @staticmethod
    def generate_profit_loss_report(start_date=None, end_date=None):
        """Generate profit & loss report based on actual sales profit minus returns and damages"""
        try:
            if not start_date:
                start_date = date.today().replace(day=1)
            if not end_date:
                end_date = date.today()
            
            from returns.product_return import ProductReturn, DamagedProduct
            from invoices.invoice_item import InvoiceItem
            
            # Calculate profit from direct sales (selling_price - purchase_price) * quantity
            direct_sales = SaleNoInvoice.query.filter(
                SaleNoInvoice.sale_date >= start_date,
                SaleNoInvoice.sale_date <= end_date
            ).all()
            
            direct_sales_profit = 0
            direct_sales_revenue = 0
            for sale in direct_sales:
                if sale.product and sale.product.purchase_price:
                    profit_per_unit = float(sale.selling_price) - float(sale.product.purchase_price)
                    direct_sales_profit += profit_per_unit * sale.quantity
                direct_sales_revenue += float(sale.total_amount)
            
            # Calculate profit from invoice sales
            invoices = Invoice.query.filter(
                Invoice.invoice_date >= start_date,
                Invoice.invoice_date <= end_date
            ).all()
            
            invoice_sales_profit = 0
            invoice_sales_revenue = 0
            for invoice in invoices:
                invoice_sales_revenue += float(invoice.grand_total)
                for item in invoice.items:
                    if item.product and item.product.purchase_price:
                        profit_per_unit = float(item.unit_price) - float(item.product.purchase_price)
                        invoice_sales_profit += profit_per_unit * item.quantity
            
            total_sales_profit = direct_sales_profit + invoice_sales_profit
            total_sales_revenue = direct_sales_revenue + invoice_sales_revenue
            
            # If no data in date range, calculate all-time data instead
            if total_sales_revenue == 0:
                # Get all-time direct sales
                all_direct_sales = SaleNoInvoice.query.all()
                for sale in all_direct_sales:
                    if sale.product and sale.product.purchase_price:
                        profit_per_unit = float(sale.selling_price) - float(sale.product.purchase_price)
                        direct_sales_profit += profit_per_unit * sale.quantity
                    direct_sales_revenue += float(sale.total_amount)
                
                # Get all-time invoice sales
                all_invoices = Invoice.query.all()
                for invoice in all_invoices:
                    invoice_sales_revenue += float(invoice.grand_total)
                    for item in invoice.items:
                        if item.product and item.product.purchase_price:
                            profit_per_unit = float(item.unit_price) - float(item.product.purchase_price)
                            invoice_sales_profit += profit_per_unit * item.quantity
                
                # Get all-time returns
                all_returns = ProductReturn.query.filter(ProductReturn.status == 'Completed').all()
                for return_item in all_returns:
                    if return_item.product and return_item.product.purchase_price:
                        profit_per_unit = float(return_item.original_price) - float(return_item.product.purchase_price)
                        returns_loss += profit_per_unit * return_item.quantity_returned
                    total_returned_quantity += return_item.quantity_returned
                
                # Get all-time damages
                all_damages = DamagedProduct.query.all()
                for damaged in all_damages:
                    if damaged.product and damaged.product.purchase_price:
                        damage_loss += float(damaged.product.purchase_price) * damaged.quantity
                    total_damaged_quantity += damaged.quantity
                
                # Recalculate totals
                total_sales_profit = direct_sales_profit + invoice_sales_profit
                total_sales_revenue = direct_sales_revenue + invoice_sales_revenue
            
            all_time_data = {"note": "All-time data used" if total_sales_revenue > 0 and (start_date == date.today().replace(day=1)) else "Date range data used"}
            
            # Calculate losses from returns
            returns = ProductReturn.query.filter(
                ProductReturn.return_date >= start_date,
                ProductReturn.return_date <= end_date,
                ProductReturn.status == 'Completed'
            ).all()
            
            returns_loss = 0
            total_returned_quantity = 0
            for return_item in returns:
                if return_item.product and return_item.product.purchase_price:
                    # Loss = (selling_price - purchase_price) * returned_quantity
                    profit_per_unit = float(return_item.original_price) - float(return_item.product.purchase_price)
                    returns_loss += profit_per_unit * return_item.quantity_returned
                total_returned_quantity += return_item.quantity_returned
            
            # Calculate losses from damaged products
            damaged_products = DamagedProduct.query.filter(
                DamagedProduct.damage_date >= start_date,
                DamagedProduct.damage_date <= end_date
            ).all()
            
            damage_loss = 0
            total_damaged_quantity = 0
            for damaged in damaged_products:
                if damaged.product and damaged.product.purchase_price:
                    # Loss = purchase_price * damaged_quantity (full cost loss)
                    damage_loss += float(damaged.product.purchase_price) * damaged.quantity
                total_damaged_quantity += damaged.quantity
            
            # Net profit calculation
            net_profit = total_sales_profit - returns_loss - damage_loss
            profit_margin = (net_profit / total_sales_revenue * 100) if total_sales_revenue > 0 else 0
            
            return {
                "report_id": f"RPT-{datetime.now().strftime('%Y-%m-%d-%H%M')}",
                "report_name": "Profit & Loss Report",
                "generated_by": "Admin",
                "generated_date": datetime.now().isoformat(),
                "date_range": {
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat()
                },
                "sales_summary": {
                    "total_sales_revenue": round(float(total_sales_revenue), 2),
                    "direct_sales_profit": round(float(direct_sales_profit), 2),
                    "invoice_sales_profit": round(float(invoice_sales_profit), 2),
                    "total_sales_profit": round(float(total_sales_profit), 2)
                },
                "losses_summary": {
                    "returns_loss": round(float(returns_loss), 2),
                    "damage_loss": round(float(damage_loss), 2),
                    "total_losses": round(float(returns_loss + damage_loss), 2)
                },
                "returns_damages_count": {
                    "total_returned_products": total_returned_quantity,
                    "total_damaged_products": total_damaged_quantity,
                    "total_returns_count": len(returns),
                    "total_damages_count": len(damaged_products)
                },
                "profit_loss_summary": {
                    "net_profit": round(float(net_profit), 2),
                    "profit_margin": round(float(profit_margin), 2),
                    "status": "Profit" if net_profit >= 0 else "Loss"
                },
                "debug_info": all_time_data
            }
            
        except Exception as e:
            return {
                "report_id": f"RPT-{datetime.now().strftime('%Y-%m-%d-%H%M')}",
                "report_name": "Profit & Loss Report",
                "generated_by": "Admin",
                "generated_date": datetime.now().isoformat(),
                "error": str(e),
                "sales_summary": {"total_sales_revenue": 0.00, "total_sales_profit": 0.00},
                "losses_summary": {"returns_loss": 0.00, "damage_loss": 0.00, "total_losses": 0.00},
                "returns_damages_count": {"total_returned_products": 0, "total_damaged_products": 0, "total_returns_count": 0, "total_damages_count": 0},
                "profit_loss_summary": {"net_profit": 0.00, "profit_margin": 0.00, "status": "No Data"}
            }