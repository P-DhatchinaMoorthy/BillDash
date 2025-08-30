from customers.customer_routes import bp as customer_bp
from suppliers.supplier_routes import bp as supplier_bp
from products.product_routes import bp as product_bp
from category.category_routes import bp as category_bp
from invoices.invoice_routes import bp as invoice_bp
from payments.payment_routes import bp as payment_bp
from sales_no_invoice.sale_no_invoice_routes import bp as sale_no_invoice_bp
from purchases.purchase_routes import bp as purchase_bp
from sales.sales_routes import bp as sales_bp
from purchases.purchase_billing_routes import bp as purchase_billing_bp
from reports.report_routes import bp as report_bp
from returns.return_routes import return_bp
from user.user_routes import user_bp

def register_routes(app):
    app.register_blueprint(user_bp)
    app.register_blueprint(customer_bp, url_prefix="/customers")
    app.register_blueprint(supplier_bp, url_prefix="/suppliers")
    app.register_blueprint(product_bp, url_prefix="/products")
    app.register_blueprint(category_bp, url_prefix="/categories")
    app.register_blueprint(invoice_bp, url_prefix="/invoices")
    app.register_blueprint(payment_bp, url_prefix="/payments")
    app.register_blueprint(sale_no_invoice_bp, url_prefix="/sales-no-invoice")
    app.register_blueprint(purchase_bp, url_prefix="/purchases")
    app.register_blueprint(sales_bp, url_prefix="/sales")
    app.register_blueprint(purchase_billing_bp, url_prefix="/purchase-billing")
    app.register_blueprint(report_bp, url_prefix="/reports")
    app.register_blueprint(return_bp, url_prefix="")
    from invoices.invoice_web_routes import bp as invoice_web_bp
    app.register_blueprint(invoice_web_bp, url_prefix="/payments")
