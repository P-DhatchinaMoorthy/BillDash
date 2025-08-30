# Example of how to protect existing routes with PBAC system
# This shows how to modify customer_routes.py to use permission decorators

from flask import Blueprint, request, jsonify
from user.permission_service import require_permission, log_action
from user.auth_middleware import check_api_permission
from extensions import db
from customers.customer import Customer

# Example of protected customer routes
bp = Blueprint("customers", __name__)

@bp.route("/", methods=["POST"])
@require_permission('customers.create')
@log_action('CREATE', 'CUSTOMER')
def create_customer():
    # Original create_customer logic here
    pass

@bp.route("/", methods=["GET"])
@require_permission('customers.read')
def list_customers():
    # Original list_customers logic here
    pass

@bp.route("/<customer_id>", methods=["GET"])
@require_permission('customers.read')
def get_customer(customer_id):
    # Original get_customer logic here
    pass

@bp.route("/<customer_id>", methods=["PUT"])
@require_permission('customers.update')
@log_action('UPDATE', 'CUSTOMER')
def update_customer(customer_id):
    # Original update_customer logic here
    pass

@bp.route("/<customer_id>", methods=["DELETE"])
@require_permission('customers.delete')
@log_action('DELETE', 'CUSTOMER')
def delete_customer(customer_id):
    # Delete customer logic here
    pass

# To apply PBAC to existing routes, add these decorators:
# 1. @require_permission('module.action') - for permission checking
# 2. @log_action('ACTION', 'RESOURCE') - for audit logging
# 3. Import: from user.permission_service import require_permission, log_action

# Permission names follow the pattern: module.action
# Examples:
# - customers.create, customers.read, customers.update, customers.delete
# - products.create, products.read, products.update, products.delete
# - invoices.create, invoices.read, invoices.update, invoices.delete
# - etc.