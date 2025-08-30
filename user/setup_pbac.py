import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.main import create_app
from src.extensions import db
from user.init_data import init_roles_and_permissions, create_admin_user

def setup_pbac_system():
    """Setup the complete PBAC system"""
    app = create_app()
    
    with app.app_context():
        print("Setting up Permission-Based Access Control (PBAC) system...")
        
        # Initialize roles and permissions
        init_roles_and_permissions()
        print("✓ Roles and permissions initialized")
        
        # Create admin user
        create_admin_user()
        print("✓ Admin user created")
        
        print("\nPBAC system setup completed successfully!")
        print("Default admin credentials:")
        print("Username: admin")
        print("Password: admin123")
        print("\nPlease change the default password after first login.")

if __name__ == "__main__":
    setup_pbac_system()