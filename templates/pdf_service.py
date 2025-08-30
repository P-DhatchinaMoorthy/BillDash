# services/pdf_service.py
import pdfkit
import os
from jinja2 import Environment, FileSystemLoader
from payments.payment_service import PaymentService
from datetime import datetime

class PDFService:
    @staticmethod
    def generate_pdf_from_invoice(invoice_id):
        """
        Generate PDF directly from invoice data without intermediate HTML file
        """
        try:
            # Check if wkhtmltopdf is available
            if not PDFService.check_wkhtmltopdf():
                raise Exception("wkhtmltopdf not available")
            
            # Get invoice data
            invoice_data = PaymentService.get_detailed_invoice(invoice_id)
            if not invoice_data:
                raise Exception("Invoice not found")
            
            # Setup Jinja2 environment
            env = Environment(loader=FileSystemLoader('.'))
            template = env.get_template('invoice_template.html')
            
            # Add timestamp and set download mode
            invoice_data['generated_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            invoice_data['download_mode'] = True
            
            # Render HTML content
            html_content = template.render(**invoice_data)
            
            # PDF generation options
            options = {
                'page-size': 'A4',
                'margin-top': '0.5in',
                'margin-right': '0.5in',
                'margin-bottom': '0.5in',
                'margin-left': '0.5in',
                'encoding': "UTF-8",
                'no-outline': None,
                'enable-local-file-access': None,
                'print-media-type': None,
                'disable-smart-shrinking': None
            }
            
            # Generate PDF in memory
            pdf_content = pdfkit.from_string(html_content, False, options=options)
            
            # Generate filename
            filename = f"invoice_{invoice_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            
            return {
                'success': True,
                'pdf_content': pdf_content,
                'filename': filename,
                'invoice_data': invoice_data
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    @staticmethod
    def check_wkhtmltopdf():
        """
        Check if wkhtmltopdf is installed and accessible
        """
        try:
            import pdfkit
            # Try to create a simple PDF to test if wkhtmltopdf works
            pdfkit.from_string('<html><body>test</body></html>', False)
            return True
        except:
            return False