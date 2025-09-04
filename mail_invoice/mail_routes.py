from flask import Blueprint, request, jsonify, render_template_string
from .email_service import EmailService
import sys
import os

# Add the backend directory to the path to import other modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

mail_bp = Blueprint('mail', __name__)
email_service = EmailService()

@mail_bp.route('/send-invoice-email', methods=['POST'])
def send_invoice_email():
    """API endpoint to send invoice via email"""
    try:
        data = request.get_json()
        invoice_id = data.get('invoice_id')
        customer_email = data.get('customer_email')
        
        if not invoice_id or not customer_email:
            return jsonify({"success": False, "error": "Missing invoice_id or customer_email"})
        
        # Import required modules (adjust imports based on your project structure)
        try:
            from invoices.invoice_service import InvoiceService
            from customers.customer import Customer
            from settings.company_settings import CompanySettings
        except ImportError as e:
            return jsonify({"success": False, "error": f"Import error: {str(e)}"})
        
        # Get invoice data
        invoice_service = InvoiceService()
        invoice_data = invoice_service.get_invoice_by_id(invoice_id)
        
        if not invoice_data:
            return jsonify({"success": False, "error": "Invoice not found"})
        
        # Get customer data
        customer = Customer()
        customer_data = customer.get_customer_by_id(invoice_data.get('customer_id'))
        
        # Get company settings
        company_settings = CompanySettings()
        company_data = company_settings.get_settings()
        
        # Read the invoice template
        template_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates', 'invoice_template.html')
        with open(template_path, 'r', encoding='utf-8') as f:
            template_content = f.read()
        
        # Render the template with data (you'll need to adapt this based on your template variables)
        # This is a simplified version - you may need to adjust based on your actual data structure
        invoice_context = {
            'invoice': invoice_data,
            'customer': customer_data,
            'company_settings': company_data,
            'invoice_number': invoice_data.get('invoice_number'),
            'invoice_id': invoice_id,
            'items': invoice_data.get('items', []),
            'calculations': invoice_data.get('calculations', {}),
            'payments': invoice_data.get('payments', []),
            'summary': invoice_data.get('summary', {}),
            'amount_in_words': invoice_data.get('amount_in_words', ''),
            'generated_at': invoice_data.get('generated_at', ''),
            'currency': 'INR'
        }
        
        # Remove the buttons and scripts from HTML for PDF generation
        html_content = template_content
        # Remove the no-print sections for PDF
        html_content = html_content.replace('class="no-print"', 'style="display:none"')
        
        # Render template (simplified - you may need Jinja2 rendering)
        from jinja2 import Template
        template = Template(html_content)
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
        result = email_service.send_invoice_email(customer_email, email_invoice_data, rendered_html)
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})