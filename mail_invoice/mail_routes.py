from flask import Blueprint, request, jsonify, render_template_string
from .email_service import EmailService
from user.enhanced_auth_middleware import require_permission_jwt
from user.audit_logger import audit_decorator
import sys
import os
from datetime import datetime

# Add the backend directory to the path to import other modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

mail_bp = Blueprint('mail', __name__)
email_service = EmailService()

@mail_bp.route('/send-invoice-email', methods=['POST'])
@require_permission_jwt('invoices', 'write')
@audit_decorator('invoices', 'EMAIL_SEND')
def send_invoice_email():
    """API endpoint to send invoice via email"""
    try:
        # Handle different content types
        data = {}
        if request.is_json:
            data = request.get_json() or {}
        elif request.form:
            data = request.form.to_dict()
        
        # Fallback to args if no data found
        if not data:
            data = request.args.to_dict()
        
        # Get required parameters
        invoice_id = data.get('invoice_id')
        customer_email = data.get('customer_email')
        
        if not invoice_id or not customer_email:
            return jsonify({
                "success": False, 
                "error": "Missing invoice_id or customer_email"
            }), 400
        
        # Import required modules (adjust imports based on your project structure)
        try:
            from invoices.invoice import Invoice
            from customers.customer import Customer
            from settings.company_settings import Settings
        except ImportError as e:
            return jsonify({"success": False, "error": f"Import error: {str(e)}"})
        
        # Get invoice data
        invoice = Invoice.query.get(invoice_id)
        if not invoice:
            return jsonify({"success": False, "error": "Invoice not found"})
            
        # Get invoice items
        from invoices.invoice_item import InvoiceItem
        invoice_items = InvoiceItem.query.filter_by(invoice_id=invoice_id).all()
        
        items_data = []
        for item in invoice_items:
            from products.product import Product
            from category.category import Category
            product = Product.query.get(item.product_id)
            
            # Get HSN code from product's category if not in product
            hsn_code = 'N/A'
            if product:
                if hasattr(product, 'hsn_code') and product.hsn_code:
                    hsn_code = product.hsn_code
                elif product.category_id:
                    category = Category.query.get(product.category_id)
                    if category and category.hsn_code:
                        hsn_code = category.hsn_code
            
            items_data.append({
                'product_id': item.product_id,
                'product_name': product.product_name if product else 'Unknown Product',
                'sku': product.sku if product else 'N/A',
                'hsn_code': hsn_code,
                'quantity': item.quantity,
                'unit_price': float(item.unit_price),
                'total_price': float(item.total_price),
                'tax_rate_per_item': float(item.tax_rate_per_item),
                'unit_of_measure': product.unit_of_measure if product else 'NOS',
                'description': getattr(product, 'description', '') if product else '',
                'batch_number': getattr(product, 'batch_number', '') if product else '',
                'expiry_date': str(product.expiry_date) if product and hasattr(product, 'expiry_date') and product.expiry_date else ''
            })
        
        # Get payment status
        from payments.payment import Payment
        payments = Payment.query.filter_by(invoice_id=invoice_id).all()
        total_paid = sum(float(p.amount_paid or 0) for p in payments)
        balance_due = float(invoice.grand_total) - total_paid
        
        if balance_due <= 0:
            payment_status = 'Paid'
        elif total_paid > 0:
            payment_status = 'Partially Paid'
        else:
            payment_status = 'Pending'
        
        invoice_data = {
            'invoice_number': invoice.invoice_number,
            'invoice_date': invoice.invoice_date.strftime('%Y-%m-%d') if invoice.invoice_date else '',
            'due_date': invoice.due_date.strftime('%Y-%m-%d') if invoice.due_date else '',
            'grand_total': str(invoice.grand_total),
            'customer_id': invoice.customer_id,
            'status': invoice.status,
            'id': invoice.id,
            'tax_amount': str(invoice.tax_amount),
            'discount_amount': str(invoice.discount_amount),
            'shipping_charges': str(invoice.shipping_charges),
            'other_charges': str(invoice.other_charges),
            'total_before_tax': str(invoice.total_before_tax)
        }
        
        # Add payment summary
        summary = {
            'total_amount_paid': f'{total_paid:.2f}',
            'balance_due': f'{balance_due:.2f}',
            'payment_status': payment_status
        }

        
        # Get customer data
        customer = Customer.query.get(invoice_data.get('customer_id'))
        if customer:
            customer_data = {
                'id': customer.id,
                'contact_person': customer.contact_person or 'Unknown Customer',
                'business_name': customer.business_name or customer.contact_person,
                'email': customer.email or '',
                'phone': customer.phone or 'N/A',
                'billing_address': customer.billing_address or 'Address not provided',
                'shipping_address': customer.shipping_address or customer.billing_address or 'Address not provided',
                'payment_terms': customer.payment_terms or ''
            }
        else:
            customer_data = {
                'id': 'N/A',
                'contact_person': 'Unknown Customer',
                'business_name': 'Unknown Customer',
                'email': '',
                'phone': 'N/A',
                'billing_address': 'Address not provided',
                'shipping_address': 'Address not provided',
                'payment_terms': ''
            }
        
        # Get company settings
        company_settings = Settings.query.first()
        if company_settings:
            company_data = {
                'business_name': company_settings.business_name or 'Your Company',
                'tagline': company_settings.tagline or 'Excellence in Every Transaction',
                'primary_email': company_settings.primary_email or 'info@company.com',
                'primary_phone': company_settings.primary_phone or '+91-XXXXXXXXXX',
                'secondary_phone': company_settings.secondary_phone or 'N/A',
                'gst_number': company_settings.gst_number or 'GSTIN-XXXXXXXXX',
                'registered_address': company_settings.registered_address or 'Address not available',
                'state': company_settings.state or 'State',
                'postal_code': company_settings.postal_code or '000000',
                'website': company_settings.website or 'www.company.com',
                'bank_name': company_settings.bank_name or 'Your Bank Name',
                'account_number': company_settings.account_number or 'Your Account Number',
                'ifsc_code': company_settings.ifsc_code or 'Your IFSC Code',
                'branch': company_settings.branch or 'Your Branch'
            }
        else:
            company_data = {
                'business_name': 'Your Company',
                'tagline': 'Excellence in Every Transaction',
                'primary_email': 'info@company.com',
                'primary_phone': '+91-XXXXXXXXXX',
                'secondary_phone': 'N/A',
                'gst_number': 'GSTIN-XXXXXXXXX',
                'registered_address': 'Address not available',
                'state': 'State',
                'postal_code': '000000',
                'website': 'www.company.com'
            }
        
        # Read the invoice template
        template_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates', 'invoice_template.html')
        with open(template_path, 'r', encoding='utf-8') as f:
            template_content = f.read()
        
        # Create calculations object
        calculations = {
            'subtotal': float(invoice.total_before_tax),
            'grand_total': float(invoice.grand_total),
            'tax_amount': float(invoice.tax_amount)
        }
        
        # Convert amount to words (basic implementation)
        def number_to_words(amount):
            try:
                # Basic implementation - you can enhance this
                amount_int = int(float(amount))
                if amount_int == 0:
                    return "Zero"
                # Simple conversion for demo
                return f"Rupees {amount_int} Only"
            except:
                return "Amount conversion error"
        
        amount_in_words = number_to_words(invoice.grand_total)
        
        # Encode logo to base64
        import base64
        logo_base64 = ''
        try:
            logo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'addons', 'DMlogo.jpg')
            if os.path.exists(logo_path):
                with open(logo_path, 'rb') as logo_file:
                    logo_base64 = base64.b64encode(logo_file.read()).decode('utf-8')
        except Exception as e:
            print(f"Logo encoding error: {e}")
        
        # Use calculated summary object (already created above)
        
        # Render the template with data
        invoice_context = {
            'invoice': invoice_data,
            'customer': customer_data,
            'company_settings': company_data,
            'invoice_number': invoice_data.get('invoice_number'),
            'invoice_id': invoice_id,
            'items': items_data,
            'calculations': calculations,
            'payments': [],
            'summary': summary,
            'amount_in_words': amount_in_words,
            'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'currency': 'INR',
            'logo_base64': logo_base64
        }
        
        # Render the complete invoice template with all data
        from jinja2 import Template
        template = Template(template_content)
        rendered_html = template.render(**invoice_context)
        
        # Prepare invoice data for email
        email_invoice_data = {
            'invoice_number': invoice_data.get('invoice_number'),
            'invoice_date': invoice_data.get('invoice_date'),
            'due_date': invoice_data.get('due_date'),
            'grand_total': invoice_data.get('grand_total'),
            'customer_name': customer_data.get('contact_person', customer_data.get('name')),
            'company_name': company_data.get('business_name', 'Your Company')
        }
        
        # Send email
        # Store the rendered HTML in context
        invoice_context['html_template'] = rendered_html
        
        # Send email with complete rendered HTML and context
        result = email_service.send_invoice_email(customer_email, email_invoice_data, rendered_html, invoice_context)
        
        return jsonify(result)
        
    except Exception as e:
        print(f"DEBUG: Exception: {str(e)}")
        import traceback
        print(f"DEBUG: Traceback: {traceback.format_exc()}")
        return jsonify({"success": False, "error": str(e)})