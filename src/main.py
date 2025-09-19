import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import subprocess
from pathlib import Path
from flask import Flask, jsonify
from flask_cors import CORS
from src.config import Config
from src.extensions import db, migrate, mail
from user.user import User, Permission, UserPermission, AuditLog
from settings.company_settings import Settings

# register blueprints dynamically
from routes import register_routes

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.config['SQLALCHEMY_DATABASE_URI'] = "postgresql://postgres@127.0.0.1:5432/store_db"
    app.config['SECRET_KEY'] = 'your-secret-key-change-in-production'
    app.config['SESSION_TYPE'] = 'filesystem'

    # Enable CORS for all routes
    CORS(app, origins="*", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"], allow_headers=["Content-Type", "Authorization"], supports_credentials=True)

    # Mail configuration
    app.config['MAIL_SERVER'] = 'smtp.gmail.com'
    app.config['MAIL_PORT'] = 587
    app.config['MAIL_USE_TLS'] = True
    app.config['MAIL_USERNAME'] = 'datchu15052003@gmail.com'
    app.config['MAIL_PASSWORD'] = 'uflq lwzt tvpo vdbs'
    app.config['MAIL_DEFAULT_SENDER'] = 'datchu15052003@gmail.com'
    
    # initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    mail.init_app(app)
    
    # Import all models within app context to resolve relationships
    with app.app_context():
        from customers.customer import Customer
        from invoices.invoice import Invoice
        from invoices.invoice_item import InvoiceItem
        from payments.payment import Payment
        from products.product import Product
        from suppliers.supplier import Supplier
        from category.category import Category, SubCategory
        from stock_transactions.stock_transaction import StockTransaction

    # register routes/blueprints
    register_routes(app)
    


    @app.get("/")
    def index():
        return jsonify({"message": "Store Management API"}), 200
    
    @app.route('/api/test')
    def test():
        return jsonify({"message": "Backend Connected Successfully"}), 200
    
    @app.route('/logo.png')
    def serve_logo():
        from flask import send_file
        return send_file('logo.png', mimetype='image/png')
    
    @app.route('/addons/<filename>')
    def serve_addons(filename):
        from flask import send_file
        import os
        # Get absolute path to addons directory
        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        addon_path = os.path.join(backend_dir, 'addons', filename)
        if os.path.exists(addon_path):
            return send_file(addon_path, mimetype='image/png')
        else:
            return jsonify({"error": "File not found"}), 404

    return app



# PostgreSQL Management
PG_ROOT = "G:\\Bills\\my_embedded_pg"
PG_BIN = os.path.join(PG_ROOT, "bin")
PG_DATA = os.path.join(PG_ROOT, "data")
PG_PORT = "5432"

def is_postgres_running():
    pg_ctl = os.path.join(PG_BIN, "pg_ctl.exe")
    try:
        result = subprocess.run([
            pg_ctl, "-D", PG_DATA, "status"
        ], capture_output=True, text=True)
        return result.returncode == 0
    except:
        return False

def start_postgres():
    pg_ctl = os.path.join(PG_BIN, "pg_ctl.exe")
    if not os.path.exists(pg_ctl):
        print("ERROR: pg_ctl.exe not found.")
        return
    
    if is_postgres_running():
        print(f"PostgreSQL is already running on port {PG_PORT}")
        return
    
    try:
        subprocess.Popen([
            pg_ctl, "-D", PG_DATA, "-l", os.path.join(PG_ROOT, "postgres.log"),
            "-o", f"-p {PG_PORT}", "start"
        ])
        print(f"Starting PostgreSQL on port {PG_PORT}...")
    except Exception as e:
        print(f"Failed to start embedded Postgres: {e}")

def stop_postgres():
    if not is_postgres_running():
        return
    
    pg_ctl = os.path.join(PG_BIN, "pg_ctl.exe")
    try:
        subprocess.run([
            pg_ctl, "-D", PG_DATA, "stop", "-m", "fast"
        ], check=True, capture_output=True)
        print("PostgreSQL stopped")
    except:
        pass  # Already stopped or failed

if __name__ == "__main__":
    import logging
    import smtplib
    import atexit
    
    logging.getLogger('smtplib').setLevel(logging.ERROR)
    smtplib.SMTP.debuglevel = 0
    
    # Only start PostgreSQL in main process, not in Flask reloader
    if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        start_postgres()
        atexit.register(stop_postgres)
    
    app = create_app()
    app.run(host="0.0.0.0", port=5000, debug=app.config["DEBUG"])
