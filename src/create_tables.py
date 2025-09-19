import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from extensions import db
# Import all model files
from category.category import Category
from customers.customer import Customer
from invoices.invoice import Invoice
from invoices.invoice_item import InvoiceItem
from payments.payment import Payment
from products.product import Product
from purchases.purchase_bill import PurchaseBill
from purchases.supplier_damage import SupplierDamage
from reports.report import Report
from returns.product_return import ProductReturn, DamagedProduct
from sales_no_invoice.sale_no_invoice import SaleNoInvoice
from stock_transactions.stock_transaction import StockTransaction
from suppliers.supplier import Supplier
from user.user import User, Permission, UserPermission, AuditLog
from user.models import PasswordResetToken

def create_tables():
    db.drop_all()
    db.create_all()
    print("All tables created successfully with new schema including returns!")

if __name__ == "__main__":
    from main import create_app
    app = create_app()
    with app.app_context():
        create_tables()