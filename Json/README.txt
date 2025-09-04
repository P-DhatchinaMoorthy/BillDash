USER MANAGEMENT JSON FILES
==========================

USAGE:
------

1. CREATE USERS:
   POST http://localhost:5000/admin/create_user
   Use files: create_admin.json, create_manager.json, create_accountant.json, create_stock_manager.json, create_sales.json

2. LOGIN:
   POST http://localhost:5000/login
   Use files: login_admin.json, login_manager.json (or create similar for other users)

3. GRANT PERMISSIONS:
   POST http://localhost:5000/admin/grant-permission
   Use file: grant_permissions_example.json (modify user_id and module as needed)

4. GET USER PERMISSIONS:
   GET http://localhost:5000/admin/user-permissions/<user_id>

5. INITIALIZE USER PERMISSIONS:
   POST http://localhost:5000/admin/initialize-user-permissions/<user_id>

DEFAULT CREDENTIALS:
-------------------
- admin/admin123 (Full access)
- manager/manager123 (Business operations)
- accountant/accountant123 (Financial operations)
- stock_manager/stock123 (Inventory management)
- sales/sales123 (Sales and customer focus)

PERMISSION LEVELS:
-----------------
- read: View data
- write: Create/Update data
- delete: Remove data

MODULES:
--------
customers, suppliers, products, invoices, payments, sales, purchases, reports, returns, stock_transactions, admin