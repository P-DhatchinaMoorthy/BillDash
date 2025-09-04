import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import pdfkit
from jinja2 import Template
import tempfile
from .config import EmailConfig

class EmailService:
    def __init__(self):
        # Email configuration from config file
        self.smtp_server = EmailConfig.SMTP_SERVER
        self.smtp_port = EmailConfig.SMTP_PORT
        self.sender_email = EmailConfig.SENDER_EMAIL
        self.sender_password = EmailConfig.SENDER_PASSWORD
        
    def generate_pdf_from_html(self, html_content, invoice_number):
        """Convert HTML content to PDF and return the file path"""
        try:
            # Create temporary file for PDF
            temp_dir = tempfile.gettempdir()
            pdf_filename = f"invoice_{invoice_number}.pdf"
            pdf_path = os.path.join(temp_dir, pdf_filename)
            
            # Configure wkhtmltopdf options
            options = {
                'page-size': 'A4',
                'margin-top': '0.75in',
                'margin-right': '0.75in',
                'margin-bottom': '0.75in',
                'margin-left': '0.75in',
                'encoding': "UTF-8",
                'no-outline': None,
                'enable-local-file-access': None
            }
            
            # Generate PDF
            pdfkit.from_string(html_content, pdf_path, options=options)
            return pdf_path
            
        except Exception as e:
            print(f"Error generating PDF: {str(e)}")
            return None
    
    def send_invoice_email(self, customer_email, invoice_data, html_content):
        """Send invoice as PDF attachment via email"""
        try:
            # Generate PDF from HTML
            pdf_path = self.generate_pdf_from_html(html_content, invoice_data['invoice_number'])
            if not pdf_path:
                return {"success": False, "error": "Failed to generate PDF"}
            
            # Create message
            msg = MIMEMultipart()
            msg['From'] = self.sender_email
            msg['To'] = customer_email
            msg['Subject'] = f"Invoice #{invoice_data['invoice_number']} - {invoice_data.get('company_name', 'Your Company')}"
            
            # Email body
            body = f"""
Dear {invoice_data.get('customer_name', 'Valued Customer')},

Please find attached your invoice #{invoice_data['invoice_number']} dated {invoice_data.get('invoice_date', '')}.

Invoice Details:
- Invoice Number: {invoice_data['invoice_number']}
- Amount: ₹{invoice_data.get('grand_total', '0.00')}
- Due Date: {invoice_data.get('due_date', 'N/A')}

Thank you for your business!

Best regards,
{invoice_data.get('company_name', 'Your Company')}
            """
            
            msg.attach(MIMEText(body, 'plain'))
            
            # Attach PDF
            with open(pdf_path, "rb") as attachment:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(attachment.read())
                
            encoders.encode_base64(part)
            part.add_header(
                'Content-Disposition',
                f'attachment; filename= invoice_{invoice_data["invoice_number"]}.pdf'
            )
            msg.attach(part)
            
            # Send email
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()
            server.login(self.sender_email, self.sender_password)
            server.send_message(msg)
            server.quit()
            
            # Clean up temporary PDF file
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
            
            return {"success": True, "message": "Invoice sent successfully"}
            
        except Exception as e:
            return {"success": False, "error": str(e)}