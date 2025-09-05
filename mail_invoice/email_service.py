import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from jinja2 import Template
import tempfile
from html import unescape
import re

# Force Playwright detection
PLAYWRIGHT_AVAILABLE = False
try:
    import playwright
    from playwright.sync_api import sync_playwright
    # Test if it actually works
    with sync_playwright() as p:
        browser = p.chromium.launch()
        browser.close()
    PLAYWRIGHT_AVAILABLE = True
    print("✓ Playwright is working! Full template PDFs enabled.")
except Exception as e:
    print(f"✗ Playwright error: {e}")
    PLAYWRIGHT_AVAILABLE = False

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
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
            
            if PLAYWRIGHT_AVAILABLE:
                # Use Playwright for full HTML template PDF (like html2canvas + jsPDF)
                with sync_playwright() as p:
                    browser = p.chromium.launch()
                    page = browser.new_page()
                    
                    # Clean HTML for PDF (remove buttons)
                    clean_html = html_content.replace('class="no-print"', 'style="display:none"')
                    
                    # Set content and generate PDF
                    page.set_content(clean_html)
                    page.pdf(path=pdf_path, format='A4', print_background=True)
                    
                    browser.close()
                    return pdf_path
            else:
                # Fallback to reportlab summary
                from reportlab.lib import colors
                from reportlab.lib.pagesizes import A4
                from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
                from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
                from reportlab.lib.units import inch
                import re
                
                doc = SimpleDocTemplate(pdf_path, pagesize=A4, topMargin=0.5*inch)
                styles = getSampleStyleSheet()
                story = []
                
                # Extract invoice data from HTML
                invoice_num = re.search(r'Invoice #:.*?<b>(.*?)</b>', html_content)
                invoice_date = re.search(r'Invoice Date:.*?<b>(.*?)</b>', html_content)
                customer_name = re.search(r'<b>([^<]+)</b><br>\\s*<b>Billing address:', html_content)
                grand_total = re.search(r'Grand Total.*?₹([\\d,\\.]+)', html_content)
                
                # Title
                title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'], fontSize=20, spaceAfter=30, alignment=1)
                story.append(Paragraph(f"INVOICE {invoice_num.group(1) if invoice_num else invoice_number}", title_style))
                story.append(Spacer(1, 20))
                
                # Invoice details table
                invoice_info = [
                    ['Invoice Number:', invoice_num.group(1) if invoice_num else invoice_number],
                    ['Invoice Date:', invoice_date.group(1) if invoice_date else 'N/A'],
                    ['Customer:', customer_name.group(1) if customer_name else 'N/A'],
                    ['Grand Total:', f"₹{grand_total.group(1)}" if grand_total else 'N/A']
                ]
                
                info_table = Table(invoice_info, colWidths=[2*inch, 4*inch])
                info_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
                    ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 0), (-1, -1), 12),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black)
                ]))
                
                story.append(info_table)
                story.append(Spacer(1, 30))
                story.append(Paragraph("Install Playwright for full template PDF", styles['Heading2']))
                
                doc.build(story)
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
            
        except smtplib.SMTPAuthenticationError as e:
            print(f"SMTP Authentication Error: {e}")
            return {"success": False, "error": f"Email authentication failed: {str(e)}"}
        except smtplib.SMTPConnectError as e:
            print(f"SMTP Connection Error: {e}")
            return {"success": False, "error": f"Cannot connect to email server: {str(e)}"}
        except Exception as e:
            print(f"General Error: {e}")
            return {"success": False, "error": str(e)}