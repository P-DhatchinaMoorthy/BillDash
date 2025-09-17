"""
Enhanced Audit Logging Example

This demonstrates the new audit logging system that captures:
- Only POST, PUT, DELETE operations
- User ID, username, and role
- Resource ID (e.g., customer ID)
- Before and after data for updates
- Detailed action descriptions

Example audit log entries:

1. When manager creates a new customer:
{
    "id": 1,
    "user_id": 5,
    "username": "manager_john",
    "user_role": "manager", 
    "action": "POST_CREATE_CUSTOMER",
    "module_name": "customers",
    "record_id": 123,
    "old_data": null,
    "new_data": {
        "contact_person": "John Doe",
        "business_name": "ABC Corp",
        "phone": "1234567890",
        "email": "john@abc.com"
    },
    "ip_address": "192.168.1.100",
    "timestamp": "2024-01-15T10:30:00",
    "description": "manager_john (manager) created new customer (ID: 123) in customers module"
}

2. When admin updates customer details:
{
    "id": 2,
    "user_id": 1,
    "username": "admin_user",
    "user_role": "admin",
    "action": "PUT_UPDATE_CUSTOMER", 
    "module_name": "customers",
    "record_id": 123,
    "old_data": {
        "id": 123,
        "contact_person": "John Doe",
        "business_name": "ABC Corp",
        "phone": "1234567890",
        "email": "john@abc.com"
    },
    "new_data": {
        "contact_person": "John Smith",
        "business_name": "ABC Corporation",
        "phone": "1234567890",
        "email": "johnsmith@abc.com"
    },
    "ip_address": "192.168.1.101",
    "timestamp": "2024-01-15T11:45:00",
    "description": "admin_user (admin) updated customer (ID: 123) in customers module"
}

3. When user deletes a customer:
{
    "id": 3,
    "user_id": 7,
    "username": "user_mary",
    "user_role": "user",
    "action": "DELETE_DELETE_CUSTOMER",
    "module_name": "customers", 
    "record_id": 123,
    "old_data": {
        "id": 123,
        "contact_person": "John Smith",
        "business_name": "ABC Corporation",
        "phone": "1234567890",
        "email": "johnsmith@abc.com"
    },
    "new_data": null,
    "ip_address": "192.168.1.102",
    "timestamp": "2024-01-15T14:20:00",
    "description": "user_mary (user) deleted customer (ID: 123) in customers module"
}

Key Features:
- Only logs POST, PUT, DELETE operations (no GET requests)
- Captures user identity (ID, username, role)
- Records resource ID for tracking specific records
- Stores before/after data for audit trail
- Provides human-readable descriptions
- Includes IP address and timestamp
- Supports filtering by module, action, user, date range
"""

# Usage in your routes:

# For CREATE operations:
# @audit_decorator('customers', 'CREATE', 'customer')

# For UPDATE operations:  
# @audit_decorator('customers', 'UPDATE', 'customer')

# For DELETE operations:
# @audit_decorator('customers', 'DELETE', 'customer')

# Manual logging:
# log_user_action('CREATE', 'customers', customer_id, None, request_data, 'customer')

# View audit logs via API:
# GET /admin/audit-logs/
# GET /admin/audit-logs/?module=customers
# GET /admin/audit-logs/?action=CREATE
# GET /admin/audit-logs/?user_id=5
# GET /admin/audit-logs/?date_from=2024-01-01&date_to=2024-01-31