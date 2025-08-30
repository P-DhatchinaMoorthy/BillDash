from .user import User, Role, Permission, RolePermission
from .permission_service import PermissionService
from src.extensions import db

def init_roles_and_permissions():
    """Initialize default roles and permissions"""
    
    # Create roles
    roles_data = [
        {'name': 'Admin', 'description': 'Full system access'},
        {'name': 'Manager', 'description': 'Management level access'},
        {'name': 'Accountant', 'description': 'Financial operations access'},
        {'name': 'Stock Manager', 'description': 'Inventory management access'},
        {'name': 'Sales', 'description': 'Sales operations access'}
    ]
    
    for role_data in roles_data:
        if not Role.query.filter_by(name=role_data['name']).first():
            role = Role(**role_data)
            db.session.add(role)
    
    db.session.commit()
    
    # Create permissions
    permissions_data = [
        # Customer permissions
        {'name': 'customers.create', 'module': 'customers', 'action': 'create'},
        {'name': 'customers.read', 'module': 'customers', 'action': 'read'},
        {'name': 'customers.update', 'module': 'customers', 'action': 'update'},
        {'name': 'customers.delete', 'module': 'customers', 'action': 'delete'},
        
        # Supplier permissions
        {'name': 'suppliers.create', 'module': 'suppliers', 'action': 'create'},
        {'name': 'suppliers.read', 'module': 'suppliers', 'action': 'read'},
        {'name': 'suppliers.update', 'module': 'suppliers', 'action': 'update'},
        {'name': 'suppliers.delete', 'module': 'suppliers', 'action': 'delete'},
        
        # Category permissions
        {'name': 'categories.create', 'module': 'categories', 'action': 'create'},
        {'name': 'categories.read', 'module': 'categories', 'action': 'read'},
        {'name': 'categories.update', 'module': 'categories', 'action': 'update'},
        {'name': 'categories.delete', 'module': 'categories', 'action': 'delete'},
        
        # Product permissions
        {'name': 'products.create', 'module': 'products', 'action': 'create'},
        {'name': 'products.read', 'module': 'products', 'action': 'read'},
        {'name': 'products.update', 'module': 'products', 'action': 'update'},
        {'name': 'products.delete', 'module': 'products', 'action': 'delete'},
        
        # Invoice permissions
        {'name': 'invoices.create', 'module': 'invoices', 'action': 'create'},
        {'name': 'invoices.read', 'module': 'invoices', 'action': 'read'},
        {'name': 'invoices.update', 'module': 'invoices', 'action': 'update'},
        {'name': 'invoices.delete', 'module': 'invoices', 'action': 'delete'},
        
        # Payment permissions
        {'name': 'payments.create', 'module': 'payments', 'action': 'create'},
        {'name': 'payments.read', 'module': 'payments', 'action': 'read'},
        {'name': 'payments.update', 'module': 'payments', 'action': 'update'},
        {'name': 'payments.delete', 'module': 'payments', 'action': 'delete'},
        
        # Purchase permissions
        {'name': 'purchases.create', 'module': 'purchases', 'action': 'create'},
        {'name': 'purchases.read', 'module': 'purchases', 'action': 'read'},
        {'name': 'purchases.update', 'module': 'purchases', 'action': 'update'},
        {'name': 'purchases.delete', 'module': 'purchases', 'action': 'delete'},
        
        # Return permissions
        {'name': 'returns.create', 'module': 'returns', 'action': 'create'},
        {'name': 'returns.read', 'module': 'returns', 'action': 'read'},
        {'name': 'returns.update', 'module': 'returns', 'action': 'update'},
        {'name': 'returns.delete', 'module': 'returns', 'action': 'delete'},
        
        # Report permissions
        {'name': 'reports.read', 'module': 'reports', 'action': 'read'},
        {'name': 'reports.generate', 'module': 'reports', 'action': 'generate'},
        
        # User permissions
        {'name': 'users.create', 'module': 'users', 'action': 'create'},
        {'name': 'users.read', 'module': 'users', 'action': 'read'},
        {'name': 'users.update', 'module': 'users', 'action': 'update'},
        {'name': 'users.delete', 'module': 'users', 'action': 'delete'},
        
        # Audit permissions
        {'name': 'audit.read', 'module': 'audit', 'action': 'read'}
    ]
    
    for perm_data in permissions_data:
        if not Permission.query.filter_by(name=perm_data['name']).first():
            permission = Permission(**perm_data)
            db.session.add(permission)
    
    db.session.commit()
    
    # Assign permissions to roles
    roles = Role.query.all()
    for role in roles:
        permissions = PermissionService.get_permissions_for_role(role.name)
        
        for perm_name in permissions:
            existing = RolePermission.query.filter_by(
                role_id=role.id,
                permission_name=perm_name
            ).first()
            
            if not existing:
                role_perm = RolePermission(
                    role_id=role.id,
                    permission_name=perm_name,
                    granted=True
                )
                db.session.add(role_perm)
    
    db.session.commit()

def create_admin_user():
    """Create default admin user"""
    admin_role = Role.query.filter_by(name='Admin').first()
    
    if not User.query.filter_by(username='admin').first():
        admin_user = User(
            username='admin',
            email='admin@company.com',
            role_id=admin_role.id
        )
        admin_user.set_password('admin123')
        db.session.add(admin_user)
        db.session.commit()
        print("Default admin user created: username=admin, password=admin123")