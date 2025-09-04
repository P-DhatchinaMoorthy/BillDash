from src.extensions import db

# Import all models so migrations can detect them
from customers.customer import Customer
from suppliers.supplier import Supplier
from category.category import Category
from products.product import Product
from invoices.invoice import Invoice
from invoices.invoice_item import InvoiceItem
from payments.payment import Payment
from stock_transactions.stock_transaction import StockTransaction
from sales_no_invoice.sale_no_invoice import SaleNoInvoice
from purchases.purchase_bill import PurchaseBill
from returns.product_return import ProductReturn, DamagedProduct


__all__ = [
    "db",
    "Customer",
    "Supplier",
    "Category",
    "Product",
    "Invoice",
    "InvoiceItem",
    "Payment",
    "StockTransaction",
    "SaleNoInvoice",
    "SubCategory",
    "PurchaseBill",
    "ProductReturn",
    "DamagedProduct",
]
