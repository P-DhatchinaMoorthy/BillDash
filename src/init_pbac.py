import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask
from extensions import db
from user.user import User, Permission, UserPermission
from src.config import Config

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)
    return app

def init_permissions():
    """Create default permissions for all modules"""
    modules = [
        'customers', 'suppliers', 'products', 'categories', 
        'invoices', 'payments', 'purchases',
        'reports', 'returns', 'admin', 'settings'
    ]
    
    for module in modules:
        existing = Permission.query.filter_by(module_name=module).first()
        if not existing:
            permission = Permission(
                module_name=module,
                description=f"Access to {module} module"
            )
            db.session.add(permission)
            print(f"Created permission for {module}")
    
    db.session.commit()
    print("✓ Default permissions created")

def create_admin_user():
    """Create default admin user"""
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin = User(
            username='admin',
            password='admin123',  # In production, use proper password hashing
            role='admin'
        )
        db.session.add(admin)
        db.session.commit()
        print("✓ Admin user created (username: admin, password: admin123)")
    else:
        print("✓ Admin user already exists")
    
    return admin

def create_sample_users():
    """Create sample users with different roles"""
    users_data = [
        {'username': 'manager', 'password': 'manager123', 'role': 'manager'},
        {'username': 'accountant', 'password': 'accountant123', 'role': 'accountant'},
        {'username': 'sales', 'password': 'sales123', 'role': 'sales'},
        {'username': 'stock_manager', 'password': 'stock123', 'role': 'stock_manager'}
    ]
    
    for user_data in users_data:
        existing = User.query.filter_by(username=user_data['username']).first()
        if not existing:
            user = User(**user_data)
            db.session.add(user)
            print(f"✓ Created user: {user_data['username']}")
    
    db.session.commit()

def setup_default_permissions():
    """Setup default permissions for different roles"""
    
    # Permission matrix based on the specification
    role_permissions = {
        'manager': {
            'customers': {'read': True, 'write': True, 'delete': False},
            'suppliers': {'read': True, 'write': True, 'delete': False},
            'products': {'read': True, 'write': True, 'delete': False},
            'categories': {'read': True, 'write': True, 'delete': False},
            'invoices': {'read': True, 'write': True, 'delete': False},
            'payments': {'read': True, 'write': True, 'delete': False},
            'purchases': {'read': True, 'write': True, 'delete': False},
            'reports': {'read': True, 'write': False, 'delete': False},
            'returns': {'read': True, 'write': True, 'delete': False}
        },
        'accountant': {
            'customers': {'read': True, 'write': True, 'delete': False},
            'suppliers': {'read': True, 'write': False, 'delete': False},
            'products': {'read': True, 'write': False, 'delete': False},
            'categories': {'read': True, 'write': False, 'delete': False},
            'invoices': {'read': True, 'write': True, 'delete': False},
            'payments': {'read': True, 'write': True, 'delete': False},
            'purchases': {'read': True, 'write': False, 'delete': False},
            'reports': {'read': True, 'write': False, 'delete': False},
            'returns': {'read': True, 'write': False, 'delete': False}
        },
        'sales': {
            'customers': {'read': True, 'write': False, 'delete': False},
            'suppliers': {'read': False, 'write': False, 'delete': False},
            'products': {'read': True, 'write': False, 'delete': False},
            'categories': {'read': True, 'write': False, 'delete': False},
            'invoices': {'read': False, 'write': False, 'delete': False},
            'payments': {'read': True, 'write': True, 'delete': False},
            'purchases': {'read': False, 'write': False, 'delete': False},
            'reports': {'read': True, 'write': False, 'delete': False},
            'returns': {'read': True, 'write': True, 'delete': False}
        },
        'stock_manager': {
            'customers': {'read': False, 'write': False, 'delete': False},
            'suppliers': {'read': True, 'write': True, 'delete': False},
            'products': {'read': True, 'write': True, 'delete': False},
            'categories': {'read': True, 'write': True, 'delete': False},
            'invoices': {'read': False, 'write': False, 'delete': False},
            'payments': {'read': False, 'write': False, 'delete': False},
            'purchases': {'read': True, 'write': True, 'delete': False},
            'reports': {'read': True, 'write': False, 'delete': False},
            'returns': {'read': True, 'write': True, 'delete': False}
        }
    }
    
    for role, modules in role_permissions.items():
        user = User.query.filter_by(role=role).first()
        if not user:
            continue
            
        for module_name, perms in modules.items():
            permission = Permission.query.filter_by(module_name=module_name).first()
            if not permission:
                continue
                
            # Check if user permission already exists
            existing = UserPermission.query.filter_by(
                user_id=user.id, 
                permission_id=permission.id
            ).first()
            
            if not existing:
                user_perm = UserPermission(
                    user_id=user.id,
                    permission_id=permission.id,
                    can_read=perms['read'],
                    can_write=perms['write'],
                    can_delete=perms['delete'],
                    granted_by=1  # Admin user ID
                )
                db.session.add(user_perm)
                print(f"✓ Set permissions for {role} on {module_name}")
    
    db.session.commit()

def main():
    """Initialize the PBAC system"""
    app = create_app()
    
    with app.app_context():
        print("🚀 Initializing PBAC System...")
        
        # Create tables
        db.create_all()
        print("✓ Database tables created")
        
        # Initialize permissions
        init_permissions()
        
        # Create admin user
        admin = create_admin_user()
        
        # Create sample users
        create_sample_users()
        
        # Setup default permissions
        setup_default_permissions()
        
        print("\n🎉 PBAC System initialized successfully!")
        print("\nDefault Users Created:")
        print("- admin/admin123 (Full access)")
        print("- manager/manager123 (Business operations)")
        print("- accountant/accountant123 (Financial operations)")
        print("- sales/sales123 (Sales and customer focus)")
        print("- stock_manager/stock123 (Inventory management)")
        print("\n⚠️  Remember to change default passwords in production!")

if __name__ == "__main__":
    main()