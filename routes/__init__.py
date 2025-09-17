def register_routes(app):
    try:
        from customers.customer_routes import bp as customer_bp
        app.register_blueprint(customer_bp, url_prefix="/customers")
    except ImportError as e:
        print(f"Failed to import customer_routes: {e}")
    
    try:
        from suppliers.supplier_routes import bp as supplier_bp
        app.register_blueprint(supplier_bp, url_prefix="/suppliers")
    except ImportError as e:
        print(f"Failed to import supplier_routes: {e}")
    
    try:
        from products.product_routes import bp as product_bp
        app.register_blueprint(product_bp, url_prefix="/products")
    except ImportError as e:
        print(f"Failed to import product_routes: {e}")
    
    try:
        from category.category_routes import bp as category_bp
        app.register_blueprint(category_bp, url_prefix="/categories")
    except ImportError as e:
        print(f"Failed to import category_routes: {e}")
    
    try:
        from invoices.invoice_routes import bp as invoice_bp
        app.register_blueprint(invoice_bp, url_prefix="/invoices")
    except ImportError as e:
        print(f"Failed to import invoice_routes: {e}")
    
    try:
        from invoices.invoice_web_routes import bp as invoice_web_bp
        app.register_blueprint(invoice_web_bp, url_prefix="")
    except ImportError as e:
        print(f"Failed to import invoice_web_routes: {e}")
    
    try:
        from payments.payment_routes import bp as payment_bp
        app.register_blueprint(payment_bp, url_prefix="/payments")
    except ImportError as e:
        print(f"Failed to import payment_routes: {e}")
    
    try:
        from sales_no_invoice.sale_no_invoice_routes import bp as sale_no_invoice_bp
        app.register_blueprint(sale_no_invoice_bp, url_prefix="/sales-no-invoice")
    except ImportError as e:
        print(f"Failed to import sale_no_invoice_routes: {e}")
    
    try:
        from purchases.purchase_routes import bp as purchase_bp
        app.register_blueprint(purchase_bp, url_prefix="/purchases")
    except ImportError as e:
        print(f"Failed to import purchase_routes: {e}")
    
    # Sales module removed
    # try:
    #     from sales.sales_routes import bp as sales_bp
    #     app.register_blueprint(sales_bp, url_prefix="/sales")
    # except ImportError as e:
    #     print(f"Failed to import sales_routes: {e}")
    
    try:
        from purchases.purchase_billing_routes import bp as purchase_billing_bp
        app.register_blueprint(purchase_billing_bp, url_prefix="/purchase-billing")
    except ImportError as e:
        print(f"Failed to import purchase_billing_routes: {e}")
    
    try:
        from reports.report_routes import bp as report_bp
        app.register_blueprint(report_bp, url_prefix="/reports")
    except ImportError as e:
        print(f"Failed to import report_routes: {e}")
    
    try:
        from returns.return_routes import return_bp
        app.register_blueprint(return_bp, url_prefix="")
    except ImportError as e:
        print(f"Failed to import return_routes: {e}")
    
    try:
        from damage.damage_routes import damage_bp
        app.register_blueprint(damage_bp, url_prefix="/damage")
    except ImportError as e:
        print(f"Failed to import damage_routes: {e}")
    
    try:
        from user.user_routes import bp as user_bp
        app.register_blueprint(user_bp, url_prefix="")
    except ImportError as e:
        print(f"Failed to import user_routes: {e}")
    
    try:
        from settings.settings_routes import bp as settings_bp
        app.register_blueprint(settings_bp, url_prefix="/settings")
    except ImportError as e:
        print(f"Failed to import settings_routes: {e}")
    
    try:
        from mail_invoice.mail_routes import mail_bp
        app.register_blueprint(mail_bp, url_prefix="")
    except ImportError as e:
        print(f"Failed to import mail_routes: {e}")
    
    try:
        from user.password_reset_routes import bp as password_reset_bp
        app.register_blueprint(password_reset_bp, url_prefix="")
    except ImportError as e:
        print(f"Failed to import password_reset_routes: {e}")
    
    try:
        from user.audit_routes import bp as audit_bp
        app.register_blueprint(audit_bp, url_prefix="/admin")
    except ImportError as e:
        print(f"Failed to import audit_routes: {e}")
