from flask import Blueprint, jsonify, request, make_response, send_file
from payments.payment_service import PaymentService
from templates.pdf_service import PDFService
import os
import io

bp = Blueprint("invoice_web", __name__)

@bp.route("/invoice/<int:invoice_id>/details/index.html", methods=["GET"])
def invoice_html_view(invoice_id):
    """
    Display invoice as HTML with download button
    """
    try:
        # Get invoice data
        invoice_data = PaymentService.get_detailed_invoice(invoice_id)
        if not invoice_data:
            return jsonify({"error": "Invoice not found"}), 404
        
        # Render HTML template from root directory
        from jinja2 import Environment, FileSystemLoader
        env = Environment(loader=FileSystemLoader('.'))
        template = env.get_template('invoice_template.html')
        html_content = template.render(**invoice_data)
        return html_content
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route("/invoice/<int:invoice_id>/download", methods=["POST"])
def download_invoice_pdf(invoice_id):
    """
    Generate and download PDF directly from invoice data
    """
    try:
        # Generate PDF using PDF service
        result = PDFService.generate_pdf_from_invoice(invoice_id)
        
        if not result['success']:
            return jsonify({"error": result['error']}), 500
        
        # Create file-like object from PDF content
        pdf_buffer = io.BytesIO(result['pdf_content'])
        pdf_buffer.seek(0)
        
        # Return PDF as downloadable file
        return send_file(
            pdf_buffer,
            as_attachment=True,
            download_name=result['filename'],
            mimetype='application/pdf'
        )
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route("/invoice/<int:invoice_id>/received/index.html", methods=["GET"])
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
        
        # Render received payment template
        from jinja2 import Environment, FileSystemLoader
        from datetime import datetime
        
        env = Environment(loader=FileSystemLoader('.'))
        template = env.get_template('invoice_received_template.html')
        invoice_data['generated_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        html_content = template.render(**invoice_data)
        return html_content
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route("/invoice/<int:invoice_id>/download/html", methods=["POST"])
def download_invoice_html(invoice_id):
    """
    Fallback: Download clean HTML if PDF generation fails
    """
    try:
        # Get invoice data
        invoice_data = PaymentService.get_detailed_invoice(invoice_id)
        if not invoice_data:
            return jsonify({"error": "Invoice not found"}), 404
        
        # Render HTML template for download
        from jinja2 import Environment, FileSystemLoader
        from datetime import datetime
        
        env = Environment(loader=FileSystemLoader('.'))
        template = env.get_template('invoice_template.html')
        invoice_data['generated_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        html_content = template.render(**invoice_data, download_mode=True)
        
        response = make_response(html_content)
        response.headers['Content-Type'] = 'text/html'
        response.headers['Content-Disposition'] = f'attachment; filename=invoice_{invoice_id}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.html'
        return response
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route("/invoice/<int:invoice_id>/received/download", methods=["POST"])
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
        
        # Render received payment template for download
        from jinja2 import Environment, FileSystemLoader
        from datetime import datetime
        
        env = Environment(loader=FileSystemLoader('.'))
        template = env.get_template('invoice_received_template.html')
        invoice_data['generated_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        html_content = template.render(**invoice_data, download_mode=True)
        
        response = make_response(html_content)
        response.headers['Content-Type'] = 'text/html'
        response.headers['Content-Disposition'] = f'attachment; filename=payment_received_{invoice_id}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.html'
        return response
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500