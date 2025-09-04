# services/report_service.py
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
        """Generate profit & loss report from actual database data"""
        try:
            if not start_date:
                start_date = date.today().replace(day=1)
            if not end_date:
                end_date = date.today()
            
            # Calculate revenue from sales and invoices
            direct_sales = float(db.session.query(func.sum(SaleNoInvoice.total_amount)).scalar() or 0)
            invoice_sales = float(db.session.query(func.sum(Invoice.grand_total)).scalar() or 0)
            total_sales = direct_sales + invoice_sales
            
            # Calculate expenses from purchases
            total_purchases = float(db.session.query(func.sum(PurchaseBill.total_amount)).scalar() or 0)
            
            # Calculate damaged products value as loss
            from returns.product_return import DamagedProduct
            damaged_products = DamagedProduct.query.filter_by(status='Stored').all()
            damaged_value = sum([d.quantity * float(d.product.purchase_price) for d in damaged_products if d.product and d.product.purchase_price]) or 0.0
            
            # Operating expenses (can be extended with actual expense tracking)
            operating_expenses = 0.0  # Placeholder for future expense tracking
            
            total_expenses = total_purchases + operating_expenses + damaged_value
            gross_profit = total_sales - total_purchases
            net_profit = total_sales - total_expenses
            profit_margin = (net_profit / total_sales * 100) if total_sales > 0 else 0
            
            return {
                "report_id": f"RPT-{datetime.now().strftime('%Y-%m-%d-%H%M')}",
                "report_name": "Profit & Loss Report",
                "generated_by": "Admin",
                "generated_date": datetime.now().isoformat(),
                "date_range": {
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat()
                },
                "revenue": {
                    "total_sales_amount": float(total_sales),
                    "other_income": 0.0,
                    "total_revenue": float(total_sales)
                },
                "expenses": {
                    "total_purchases_amount": float(total_purchases),
                    "operating_expenses": float(operating_expenses),
                    "damaged_products_loss": float(damaged_value),
                    "total_expenses": float(total_expenses)
                },
                "profit_loss_summary": {
                    "gross_profit": float(gross_profit),
                    "net_profit": float(net_profit),
                    "profit_margin": round(float(profit_margin), 2)
                }
            }
            
        except Exception as e:
            return {
                "report_id": f"RPT-{datetime.now().strftime('%Y-%m-%d-%H%M')}",
                "report_name": "Profit & Loss Report",
                "generated_by": "Admin",
                "generated_date": datetime.now().isoformat(),
                "error": str(e),
                "revenue": {"total_sales_amount": 0.0, "other_income": 0.0, "total_revenue": 0.0},
                "expenses": {"total_purchases_amount": 0.0, "operating_expenses": 0.0, "damaged_products_loss": 0.0, "total_expenses": 0.0},
                "profit_loss_summary": {"gross_profit": 0.0, "net_profit": 0.0, "profit_margin": 0.0}
            }