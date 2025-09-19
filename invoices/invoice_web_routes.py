from flask import Blueprint, jsonify, request, make_response, send_file
from payments.payment_service import PaymentService
from templates.pdf_service import PDFService
from settings.company_settings import Settings
from user.enhanced_auth_middleware import require_permission_jwt
import os
import io
from jinja2 import Environment, FileSystemLoader
from datetime import datetime

# Get absolute path to templates directory
TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'templates')

bp = Blueprint("invoice_web", __name__)

@bp.route("/invoices/index.html", methods=["GET"])
@require_permission_jwt('invoices', 'read')
def invoice_index():
    """
    Serve the main invoice display page from templates
    """
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
    template = env.get_template('index.html')
    return template.render()

@bp.route("/invoice/<int:invoice_id>/details/<template_name>.html", methods=["GET"])
@require_permission_jwt('invoices', 'read')
def invoice_template_view(invoice_id, template_name):
    """
    Display invoice using different templates
    """
    try:
        # Available templates
        available_templates = {
            "index": "invoice_template.html",
            "template1": "template1.html",
            "template2": "template2.html",
            "template3": "template3.html",
            "template4": "template4.html",
            "template5": "template5.html",
            "template6": "template6.html",
            "template7": "template7.html",
            "template8": "template8.html",
            "template9": "template9.html",
            "template10": "template10.html",
            "template11": "template11.html"
        }
        
        if template_name not in available_templates:
            return jsonify({"error": "Template not found"}), 404
        
        # Get invoice data
        invoice_data = PaymentService.get_detailed_invoice(invoice_id)
        if not invoice_data:
            return jsonify({"error": "Invoice not found"}), 404
        
        # Get company settings
        company_settings = Settings.query.first()
        
        # Render HTML template from templates directory
        env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
        template = env.get_template(available_templates[template_name])
        invoice_data['generated_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # Add base URL for images
        invoice_data['base_url'] = request.host_url.rstrip('/')
        invoice_data['company_settings'] = company_settings
        html_content = template.render(**invoice_data)
        return html_content
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route("/invoice/<int:invoice_id>/download", methods=["POST"])
@require_permission_jwt('invoices', 'read')
def download_invoice_pdf(invoice_id):
    """
    Generate and download PDF using weasyprint
    """
    try:
        # Get invoice data
        invoice_data = PaymentService.get_detailed_invoice(invoice_id)
        if not invoice_data:
            return jsonify({"error": "Invoice not found"}), 404
        
        # Get company settings
        company_settings = Settings.query.first()
        
        # Render HTML template
        env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
        template = env.get_template('invoice_template.html')
        invoice_data['generated_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        invoice_data['base_url'] = request.host_url.rstrip('/')
        invoice_data['company_settings'] = company_settings
        html_content = template.render(**invoice_data, download_mode=True)
        
        # Generate PDF using weasyprint
        try:
            from weasyprint import HTML, CSS
            pdf_buffer = io.BytesIO()
            HTML(string=html_content).write_pdf(pdf_buffer)
            pdf_buffer.seek(0)
            
            return send_file(
                pdf_buffer,
                as_attachment=True,
                download_name=f'invoice_{invoice_id}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf',
                mimetype='application/pdf'
            )
        except ImportError:
            # Fallback to HTML download if weasyprint not available
            response = make_response(html_content)
            response.headers['Content-Type'] = 'text/html'
            response.headers['Content-Disposition'] = f'attachment; filename=invoice_{invoice_id}.html'
            return response
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route("/invoice/<int:invoice_id>/received/index.html", methods=["GET"])
@require_permission_jwt('invoices', 'read')
def invoice_received_html_view(invoice_id):
    """
    Display received payment confirmation as HTML for fully paid invoices
    """
    try:
        # Get invoice data
        invoice_data = PaymentService.get_detailed_invoice(invoice_id)
        if not invoice_data:
            return jsonify({"error": "Invoice not found"}), 404
        
        # Only show received template if invoice is fully paid
        if invoice_data['summary']['payment_status'] != 'Paid':
            return jsonify({"error": "Invoice is not fully paid yet"}), 400
        
        # Get company settings
        company_settings = Settings.query.first()
        
        # Render received payment template
        env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
        template = env.get_template('invoice_received_template.html')
        invoice_data['generated_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # Add base URL for images
        invoice_data['base_url'] = request.host_url.rstrip('/')
        invoice_data['company_settings'] = company_settings
        html_content = template.render(**invoice_data)
        return html_content
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route("/invoice/<int:invoice_id>/download/html", methods=["POST"])
@require_permission_jwt('invoices', 'read')
def download_invoice_html(invoice_id):
    """
    Fallback: Download clean HTML if PDF generation fails
    """
    try:
        # Get invoice data
        invoice_data = PaymentService.get_detailed_invoice(invoice_id)
        if not invoice_data:
            return jsonify({"error": "Invoice not found"}), 404
        
        # Get company settings
        company_settings = Settings.query.first()
        
        # Render HTML template for download
        env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
        template = env.get_template('invoice_template.html')
        invoice_data['generated_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # Add base URL for images
        invoice_data['base_url'] = request.host_url.rstrip('/')
        invoice_data['company_settings'] = company_settings
        html_content = template.render(**invoice_data, download_mode=True)
        
        response = make_response(html_content)
        response.headers['Content-Type'] = 'text/html'
        response.headers['Content-Disposition'] = f'attachment; filename=invoice_{invoice_id}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.html'
        return response
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route("/invoice/<int:invoice_id>/received/download", methods=["POST"])
@require_permission_jwt('invoices', 'read')
def download_received_invoice_html(invoice_id):
    """
    Download received payment confirmation as HTML
    """
    try:
        # Get invoice data
        invoice_data = PaymentService.get_detailed_invoice(invoice_id)
        if not invoice_data:
            return jsonify({"error": "Invoice not found"}), 404
        
        # Only allow download if invoice is fully paid
        if invoice_data['summary']['payment_status'] != 'Paid':
            return jsonify({"error": "Invoice is not fully paid yet"}), 400
        
        # Get company settings
        company_settings = Settings.query.first()
        
        # Render received payment template for download
        env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
        template = env.get_template('invoice_received_template.html')
        invoice_data['generated_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # Add base URL for images
        invoice_data['base_url'] = request.host_url.rstrip('/')
        invoice_data['company_settings'] = company_settings
        html_content = template.render(**invoice_data, download_mode=True)
        
        response = make_response(html_content)
        response.headers['Content-Type'] = 'text/html'
        response.headers['Content-Disposition'] = f'attachment; filename=payment_received_{invoice_id}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.html'
        return response
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500