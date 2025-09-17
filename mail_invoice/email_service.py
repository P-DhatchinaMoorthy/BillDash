import smtplib
import os
import re
import tempfile
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from jinja2 import Template
from html import unescape
from contextlib import contextmanager

# Optional imports (fallbacks are handled at runtime)
try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except Exception:
    BS4_AVAILABLE = False

# Playwright detection (attempts to run a headless launch to verify availability)
PLAYWRIGHT_AVAILABLE = False
try:
    import playwright
    from playwright.sync_api import sync_playwright
    # Try a lightweight check (wfefill still succeed in most CI/dev setups)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
        PLAYWRIGHT_AVAILABLE = True
    except Exception:
        PLAYWRIGHT_AVAILABLE = False
except Exception:
    PLAYWRIGHT_AVAILABLE = False

# Config import (expecting an object EmailConfig with required attributes)
from .config import EmailConfig

# Configure a module-level logger
logger = logging.getLogger("EmailService")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)


class EmailService:
    """EmailService encapsulates HTML-to-PDF generation and emailing invoices.

    Key features/refactors applied:
      - Consistent 1px margins for Playwright, WeasyPrint (via @page), and ReportLab
      - Safer resource management (context managers / try/finally)
      - Optional BeautifulSoup DOM insertion for the payment section (safer than blind string replace)
      - Centralized HTML sanitization helper
      - Logging instead of prints
      - SMTP `with` context usage
      - Temporary file handling with NamedTemporaryFile (deleted after send)
    """

    def __init__(self):
        # Email configuration from config file
        self.smtp_server = EmailConfig.SMTP_SERVER
        self.smtp_port = EmailConfig.SMTP_PORT
        self.sender_email = EmailConfig.SENDER_EMAIL
        self.sender_password = EmailConfig.SENDER_PASSWORD

    # ------------------------- Helpers ------------------------- #
    def sanitize_html(self, html_content: str) -> str:
        """Sanitize HTML by removing script tags and hiding no-print elements.

        We intentionally keep most of the HTML intact so renderers (Playwright/WeasyPrint)
        can use the exact template, but remove scripts which may block rendering or
        attempt network calls.
        """
        if not html_content:
            return html_content or ""

        # Remove <script> blocks (keep inline attributes intact)
        clean_html = re.sub(r"<script[^>]*>.*?</script>", "", html_content, flags=re.DOTALL | re.IGNORECASE)

        # Replace common `no-print` class usages with inline style to hide in print/email
        clean_html = clean_html.replace('class="no-print"', 'style="display:none"')
        clean_html = clean_html.replace("class='no-print'", 'style="display:none"')

        return clean_html

    def insert_payment_section(self, html_content: str, full_context: dict) -> str:
        """Insert a standardized payment section into the invoice HTML.

        If BeautifulSoup is available we do a DOM-aware insertion before the first
        table with class `item-cell`. Otherwise fall back to a safe string-insert
        attempt (less reliable but non-blocking).
        """
        if not full_context:
            return html_content

        summary = full_context.get("summary", {}) or {}

        payment_section = f"""
        <div class="amount-section" style="background-color: #f9f9f9; margin-top: 10px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 10px;">
            <div style="flex: 1;">
              <p class="bold">Payment Details:</p>
              <p>• Amount Paid ₹0.00 via Pending on 2025-09-06</p>
              <p class="bold">Total Paid: ₹{summary.get('total_amount_paid', '0.00')} | Balance Due: ₹{summary.get('balance_due', '0.00')}</p>
            </div>
            <div style="display: flex; align-items: center; justify-content: center; min-width: 200px; margin-right: 60px;">
              <h2 style="font-size: 20px; font-weight: bold; margin: 0; color: black; text-align: right;">
                PAYMENT : <b style="color: red;">{summary.get('payment_status', 'PENDING').upper()}</b>
              </h2>
            </div>
          </div>
        </div>
        """

        try:
            if BS4_AVAILABLE:
                soup = BeautifulSoup(html_content, "html.parser")
                table = soup.find("table", attrs={"class": "item-cell"})
                if table:
                    table.insert_before(BeautifulSoup(payment_section, "html.parser"))
                    return str(soup)
            # Fallback string replace (try to be tolerant of attribute ordering)
            marker = '<table class="item-cell"'
            idx = html_content.find(marker)
            if idx != -1:
                return html_content[:idx] + payment_section + html_content[idx:]
        except Exception as e:
            logger.warning("Failed to insert payment section via BeautifulSoup: %s", str(e))

        # If none of the above worked, return original content
        return html_content

    def _inject_common_css(self, html_content: str) -> str:
        """Inject a consistent CSS snippet used for PDF/email rendering.

        Critically this sets the `@page { margin: 1px }` for weasyprint and provides
        small default sizes for print.
        """
        css_block = """
        <style>
        /* Enforce 1px page margins for paged renderers */
        @page { margin: 1px !important; }

        /* Basic print/email friendly rules */
        .page-break { display: none !important; }
        .invoice-box { height: auto !important; min-height: auto !important; }
        body { font-size: 10px !important; }
        table { font-size: 10px !important; }
        th, td { padding: 3px !important; font-size: 10px !important; }
        .amount-section { margin-top: 5px !important; display: block !important; font-size: 12px !important; }
        .amount-section p { font-size: 12px !important; }
        .amount-section h2 { font-size: 20px !important; }
        p { margin: 2px 0 !important; }
        </style>
        """

        if "</head>" in html_content.lower():
            # Case-insensitive replace of </head>
            parts = re.split(r"(</head>)", html_content, flags=re.IGNORECASE)
            for i, part in enumerate(parts):
                if part.lower() == "</head>":
                    parts[i] = css_block + part
                    break
            return "".join(parts)
        else:
            # Prepend to HTML if no head tag
            return css_block + html_content

    # --------------------- PDF Generation ---------------------- #
    def generate_pdf_from_html(self, html_content: str, invoice_number: str, full_context: dict = None) -> str:
        """Convert HTML content to a PDF saved to a temporary path and return that path.

        Order of attempts:
          1) Playwright (best fidelity) — with margins set to 1px
          2) WeasyPrint (CSS-aware) — injects @page margin 1px
          3) ReportLab simplified summary PDF (always available in pure-Python envs)
        """
        if not html_content:
            logger.error("No HTML content provided to generate_pdf_from_html")
            return None

        # Ensure payment section exists
        html_content = self.insert_payment_section(html_content, full_context or {})

        # Sanitize and inject consistent CSS
        html_content = self.sanitize_html(html_content)
        html_content = self._inject_common_css(html_content)

        # Create a temporary file path for the PDF
        tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=f"_invoice_{invoice_number}.pdf")
        pdf_path = tmp_file.name
        tmp_file.close()

        # Attempt Playwright first
        if PLAYWRIGHT_AVAILABLE:
            try:
                from playwright.sync_api import sync_playwright
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    try:
                        page = browser.new_page()
                        # Use set_content so local CSS and inline resources render
                        page.set_content(html_content, wait_until="networkidle")
                        # Use 1px margins as required
                        page.pdf(path=pdf_path,
                                 format="A4",
                                 print_background=True,
                                 margin={"top": "1px", "right": "1px", "bottom": "1px", "left": "1px"})
                        logger.info("PDF generated using Playwright: %s", pdf_path)
                        return pdf_path
                    finally:
                        try:
                            browser.close()
                        except Exception:
                            pass
            except Exception as e:
                logger.warning("Playwright PDF generation failed; falling back. Error: %s", str(e))

        # Attempt weasyprint next
        try:
            import weasyprint
            try:
                weasyprint.HTML(string=html_content).write_pdf(pdf_path)
                logger.info("PDF generated using WeasyPrint: %s", pdf_path)
                return pdf_path
            except Exception as e:
                logger.warning("WeasyPrint failed to generate PDF: %s", str(e))
        except Exception:
            logger.info("WeasyPrint not available or import failed; skipping.")

        # Final fallback: generate a simple summary PDF using ReportLab
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import inch

            doc = SimpleDocTemplate(pdf_path,
                                    pagesize=A4,
                                    topMargin=1, bottomMargin=1, leftMargin=1, rightMargin=1)

            styles = getSampleStyleSheet()
            story = []

            # Extract some basic fields from the HTML for the summary
            invoice_num = re.search(r'Invoice\s*#?[:\s]*([A-Z0-9\-]+)', html_content, re.IGNORECASE)
            invoice_date = re.search(r'Invoice Date[:\s]*([0-9\-/]+)', html_content)
            customer_name = re.search(r'<b>([^<]+)</b>', html_content)
            grand_total = re.search(r'Grand Total.*?₹([\d,\.]+)', html_content)

            title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=20, spaceAfter=12, alignment=1)
            story.append(Paragraph(f"INVOICE {invoice_num.group(1) if invoice_num else invoice_number}", title_style))
            story.append(Spacer(1, 12))

            invoice_info = [
                ['Invoice Number:', invoice_num.group(1) if invoice_num else invoice_number],
                ['Invoice Date:', invoice_date.group(1) if invoice_date else 'N/A'],
                ['Customer:', customer_name.group(1) if customer_name else 'N/A'],
                ['Grand Total:', f"₹{grand_total.group(1)}" if grand_total else 'N/A']
            ]

            info_table = Table(invoice_info, colWidths=[2.0 * inch, 4.0 * inch])
            info_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.black)
            ]))

            story.append(info_table)
            story.append(Spacer(1, 20))
            story.append(Paragraph("Install Playwright or WeasyPrint for a full-fidelity PDF.", styles['Normal']))

            doc.build(story)
            logger.info("PDF generated using ReportLab summary: %s", pdf_path)
            return pdf_path
        except Exception as e:
            logger.error("ReportLab summary PDF generation failed: %s", str(e))
            # Clean up if file exists
            try:
                if os.path.exists(pdf_path):
                    os.remove(pdf_path)
            except Exception:
                pass
            return None

    # --------------------- Emailing --------------------------- #
    def send_invoice_email(self, customer_email: str, invoice_data: dict, html_content: str, full_invoice_context: dict = None) -> dict:
        """Send an invoice email with PDF attachment (generated from the provided HTML).

        Returns a dict with keys `success` (bool) and either `message` or `error`.
        """
        try:
            # Generate PDF from HTML with full context
            pdf_path = self.generate_pdf_from_html(html_content, invoice_data['invoice_number'], full_invoice_context)
            if not pdf_path:
                return {"success": False, "error": "Failed to generate PDF"}

            # Create message
            msg = MIMEMultipart('alternative')
            msg['From'] = self.sender_email
            msg['To'] = customer_email
            msg['Subject'] = f"Invoice #{invoice_data['invoice_number']} - {invoice_data.get('company_name', 'Your Company')}"

            # Create simple email body - don't send complex HTML template in the main message
            simple_email_body = f"""
            <html><body style="font-family: Arial, sans-serif; margin: 20px;">
            <h2 style="color: #2c3e50;">Invoice #{invoice_data['invoice_number']}</h2>
            <p>Dear {full_invoice_context.get('customer', {}).get('contact_person', 'Valued Customer')},</p>
            <p>Please find attached your invoice <strong>#{invoice_data['invoice_number']}</strong> dated {invoice_data.get('invoice_date', '')}.</p>
            <div style="background: #f8f9fa; padding: 15px; border-left: 4px solid #007bff; margin: 20px 0;">
                <h3 style="margin: 0 0 10px 0; color: #495057;">Invoice Summary:</h3>
                <p style="margin: 5px 0;"><strong>Invoice Number:</strong> {invoice_data['invoice_number']}</p>
                <p style="margin: 5px 0;"><strong>Amount:</strong> ₹{invoice_data.get('grand_total', '0.00')}</p>
                <p style="margin: 5px 0;"><strong>Due Date:</strong> {invoice_data.get('due_date', 'N/A')}</p>
                <p style="margin: 5px 0;"><strong>Status:</strong> {full_invoice_context.get('summary', {}).get('payment_status', 'Pending')}</p>
            </div>
            <p>The complete invoice details are available in the attached PDF.</p>
            <p>Thank you for your business!</p>
            <br>
            <p style="color: #6c757d;">Best regards,<br>{invoice_data.get('company_name', 'Your Company')}</p>
            </body></html>
            """

            # Attach plain text and HTML
            text_part = MIMEText(f"Please find attached Invoice #{invoice_data['invoice_number']} for ₹{invoice_data.get('grand_total', '0.00')}. Thank you for your business!", 'plain', 'utf-8')
            html_part = MIMEText(simple_email_body, 'html', 'utf-8')
            msg.attach(text_part)
            msg.attach(html_part)

            # Attach PDF
            with open(pdf_path, "rb") as attachment:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(attachment.read())
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', f'attachment; filename=invoice_{invoice_data["invoice_number"]}.pdf')
            msg.attach(part)

            # Send email using context manager to ensure closure
            with smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=30) as server:
                server.starttls()
                server.login(self.sender_email, self.sender_password)
                server.send_message(msg)

            # Clean up temporary PDF file
            try:
                if os.path.exists(pdf_path):
                    os.remove(pdf_path)
            except Exception as e:
                logger.warning("Failed to remove temporary PDF: %s", str(e))

            return {"success": True, "message": "Invoice sent successfully with PDF attachment"}

        except smtplib.SMTPAuthenticationError as e:
            logger.error("SMTP Authentication Error: %s", str(e))
            return {"success": False, "error": f"Email authentication failed: {str(e)}"}
        except smtplib.SMTPConnectError as e:
            logger.error("SMTP Connection Error: %s", str(e))
            return {"success": False, "error": f"Cannot connect to email server: {str(e)}"}
        except Exception as e:
            logger.exception("General Error while sending invoice email: %s", str(e))
            return {"success": False, "error": str(e)}

    # ------------------ Comprehensive Email Body ------------------ #
    def generate_complete_email_body(self, invoice_data: dict, full_context: dict) -> str:
        """Generate a verbose email body describing the invoice using full_context.

        This method was preserved and cleaned only slightly to use consistent `.get` calls.
        """
        if not full_context:
            return f"""
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

        invoice = full_context.get('invoice', {}) or {}
        customer = full_context.get('customer', {}) or {}
        company = full_context.get('company_settings', {}) or {}
        items = full_context.get('items', []) or []
        calculations = full_context.get('calculations', {}) or {}
        payments = full_context.get('payments', []) or []
        summary = full_context.get('summary', {}) or {}

        body_lines = []
        body_lines.append(f"Dear {customer.get('contact_person', 'Valued Customer')},\n")
        body_lines.append(f"Please find attached your detailed invoice #{invoice.get('invoice_number')} from {company.get('business_name', 'Your Company')}.\n")

        body_lines.append("=== INVOICE DETAILS ===")
        body_lines.append(f"Invoice Number: {invoice.get('invoice_number')}")
        body_lines.append(f"Invoice ID: {invoice.get('id')}")
        body_lines.append(f"Invoice Date: {invoice.get('invoice_date', '')[:10] if invoice.get('invoice_date') else 'N/A'}")
        body_lines.append(f"Due Date: {invoice.get('due_date', '')[:10] if invoice.get('due_date') else 'N/A'}")
        body_lines.append(f"Status: {invoice.get('status', 'N/A')}")

        body_lines.append("\n=== COMPANY DETAILS ===")
        body_lines.append(company.get('business_name', 'Company Name'))
        body_lines.append(company.get('tagline', ''))
        body_lines.append(f"GSTIN: {company.get('gst_number', 'N/A')}")
        body_lines.append(f"Address: {company.get('registered_address', 'N/A')}, {company.get('state', '')}, {company.get('postal_code', '')}")
        body_lines.append(f"Phone: {company.get('primary_phone', 'N/A')}")
        body_lines.append(f"Email: {company.get('primary_email', 'N/A')}")
        body_lines.append(f"Website: {company.get('website', 'N/A')}")

        body_lines.append("\n=== BANK DETAILS ===")
        body_lines.append(f"Bank Name: {company.get('bank_name', 'N/A')}")
        body_lines.append(f"Account Number: {company.get('account_number', 'N/A')}")
        body_lines.append(f"IFSC Code: {company.get('ifsc_code', 'N/A')}")
        body_lines.append(f"Branch: {company.get('branch', 'N/A')}")

        body_lines.append("\n=== CUSTOMER DETAILS ===")
        body_lines.append(f"Customer ID: {customer.get('id', 'N/A')}")
        body_lines.append(f"Contact Person: {customer.get('contact_person', 'N/A')}")
        body_lines.append(f"Business Name: {customer.get('business_name', 'N/A')}")
        body_lines.append(f"Phone: {customer.get('phone', 'N/A')}")
        body_lines.append(f"Email: {customer.get('email', 'N/A')}")
        body_lines.append(f"Billing Address: {customer.get('billing_address', 'N/A')}")
        body_lines.append(f"Shipping Address: {customer.get('shipping_address', 'N/A')}")
        body_lines.append(f"Payment Terms: {customer.get('payment_terms', 'N/A')}")

        body_lines.append("\n=== ITEMIZED DETAILS ===")
        for i, item in enumerate(items, 1):
            body_lines.append(f"{i}.\n   Product Name: {item.get('product_name', 'N/A')}")
            body_lines.append(f"   Quantity: {item.get('quantity', 0)}")
            body_lines.append(f"   Unit Price: ₹{item.get('unit_price', 0)}")
            body_lines.append(f"   Unit of Measure: {item.get('unit_of_measure', 'NOS')}")
            body_lines.append(f"   Tax Rate: {item.get('tax_rate_per_item', 0)}%")
            body_lines.append(f"   Total Price: ₹{item.get('total_price', 0)}\n")

        body_lines.append("\n=== FINANCIAL SUMMARY ===")
        body_lines.append(f"Subtotal (Taxable Amount): ₹{calculations.get('subtotal', '0.00')}")
        try:
            tax_amt = float(invoice.get('tax_amount', 0))
            body_lines.append(f"CGST: ₹{tax_amt / 2:.2f}")
            body_lines.append(f"SGST: ₹{tax_amt / 2:.2f}")
        except Exception:
            body_lines.append(f"CGST: ₹0.00")
            body_lines.append(f"SGST: ₹0.00")
        body_lines.append(f"Total Tax: ₹{calculations.get('tax_amount', '0.00')}")
        body_lines.append(f"Discount: ₹{invoice.get('discount_amount', '0.00')}")
        body_lines.append(f"Shipping Charges: ₹{invoice.get('shipping_charges', '0.00')}")
        body_lines.append(f"Other Charges: ₹{invoice.get('other_charges', '0.00')}")
        body_lines.append(f"GRAND TOTAL: ₹{calculations.get('grand_total', '0.00')}\n")

        body_lines.append(f"Amount in Words: {full_context.get('amount_in_words', 'N/A')}\n")

        if payments:
            body_lines.append("=== PAYMENT DETAILS ===")
            for payment in payments:
                body_lines.append(f"Amount Paid: ₹{payment.get('amount_paid', '0.00')}")
                body_lines.append(f"Payment Method: {payment.get('payment_method', 'N/A')}")
                body_lines.append(f"Payment Date: {payment.get('payment_date', '')[:10] if payment.get('payment_date') else 'N/A'}")
                body_lines.append(f"Transaction Reference: {payment.get('transaction_reference', 'N/A')}")
                body_lines.append(f"Discount Applied: ₹{payment.get('discount_amount', '0.00')}\n")

            body_lines.append(f"Total Amount Paid: ₹{summary.get('total_amount_paid', '0.00')}")
            body_lines.append(f"Balance Due: ₹{summary.get('balance_due', '0.00')}")
            body_lines.append(f"Payment Status: {summary.get('payment_status', 'N/A')}\n")
            if summary.get('total_excess_amount') and summary.get('total_excess_amount') != '0.00':
                body_lines.append(f"Excess Amount: ₹{summary.get('total_excess_amount', '0.00')}\n")
        else:
            body_lines.append("=== PAYMENT STATUS ===")
            body_lines.append(f"Payment Status: {summary.get('payment_status', 'Pending')}")
            body_lines.append(f"Balance Due: ₹{summary.get('balance_due', calculations.get('grand_total', '0.00'))}\n")

        body_lines.append("\n=== TERMS AND CONDITIONS ===")
        body_lines.append("1. Goods once sold cannot be taken back or exchanged.")
        body_lines.append("2. We are not the manufacturers, company will stand for warranty as per their terms and conditions.")
        body_lines.append("3. Interest @24% p.a. will be charged for uncleared bills beyond 15 days.")
        body_lines.append("4. Subject to local Jurisdiction.")
        if customer.get('payment_terms'):
            body_lines.append(f"5. Payment Terms: {customer.get('payment_terms')}")
        if invoice.get('payment_terms'):
            body_lines.append(f"6. Invoice Payment Terms: {invoice.get('payment_terms')}")

        body_lines.append("\n=== DOCUMENT INFO ===")
        body_lines.append(f"Generated on: {full_context.get('generated_at', 'N/A')}")
        body_lines.append(f"Currency: {full_context.get('currency', 'INR')}")
        body_lines.append(f"Last Updated: {invoice.get('updated_at', '')[:10] if invoice.get('updated_at') else 'N/A'}\n")

        body_lines.append("This is a digitally signed document.\n")
        body_lines.append("Thank you for your business!\n")
        body_lines.append(f"Best regards,\n{company.get('business_name', 'Your Company')}\n{company.get('primary_email', '')}\n{company.get('primary_phone', '')}")

        return "\n".join(body_lines)

    # ------------------- User Credentials Email ------------------ #
    def send_user_credentials_email(self, user_email: str, username: str, password: str, role: str) -> dict:
        """Send user credentials email when admin creates a new user.
        
        Returns a dict with keys `success` (bool) and either `message` or `error`.
        """
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['From'] = self.sender_email
            msg['To'] = user_email
            msg['Subject'] = "Your Account Credentials - BillDash"

            # Create email body
            email_body = f"""
            <html><body style="font-family: Arial, sans-serif; margin: 20px; line-height: 1.6;">
            <div style="max-width: 600px; margin: 0 auto; background: #f8f9fa; padding: 20px; border-radius: 8px;">
                <h2 style="color: #2c3e50; text-align: center; margin-bottom: 30px;">Welcome to BillDash</h2>
                
                <div style="background: white; padding: 20px; border-radius: 5px; margin-bottom: 20px;">
                    <p>Dear {username},</p>
                    <p>Your account has been created successfully by the administrator. Below are your login credentials:</p>
                    
                    <div style="background: #e9ecef; padding: 15px; border-left: 4px solid #007bff; margin: 20px 0;">
                        <h3 style="margin: 0 0 15px 0; color: #495057;">Login Credentials:</h3>
                        <p style="margin: 5px 0;"><strong>Username:</strong> {username}</p>
                        <p style="margin: 5px 0;"><strong>Password:</strong> {password}</p>
                        <p style="margin: 5px 0;"><strong>Role:</strong> {role.title()}</p>
                    </div>
                    
                    <div style="background: #fff3cd; padding: 15px; border-left: 4px solid #ffc107; margin: 20px 0;">
                        <h4 style="margin: 0 0 10px 0; color: #856404;">Important Security Notes:</h4>
                        <ul style="margin: 0; padding-left: 20px; color: #856404;">
                            <li>Please change your password after first login</li>
                            <li>Keep your credentials secure and confidential</li>
                            <li>Two-factor authentication (2FA) is required for all logins</li>
                            <li>You will receive an OTP on this email address during login</li>
                        </ul>
                    </div>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <p style="margin: 10px 0;"><strong>Now you can login using your login credentials</strong></p>
                    </div>
                    
                    <p>If you have any questions or need assistance, please contact your administrator.</p>
                </div>
                
                <div style="text-align: center; color: #6c757d; font-size: 12px; margin-top: 20px;">
                    <p>This is an automated message. Please do not reply to this email.</p>
                    <p>© BillDash</p>
                </div>
            </div>
            </body></html>
            """

            # Create plain text version
            text_body = f"""
Welcome to BillDash

Dear User,

Your account has been created successfully by the administrator. Below are your login credentials:

Username: {username}
Password: {password}
Role: {role.title()}

IMPORTANT SECURITY NOTES:
- Please change your password after first login
- Keep your credentials secure and confidential
- Two-factor authentication (2FA) is required for all logins
- You will receive an OTP on this email address during login

If you have any questions or need assistance, please contact your administrator.

This is an automated message. Please do not reply to this email.
© BillDash
            """

            # Attach plain text and HTML
            text_part = MIMEText(text_body, 'plain', 'utf-8')
            html_part = MIMEText(email_body, 'html', 'utf-8')
            msg.attach(text_part)
            msg.attach(html_part)

            # Send email
            with smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=30) as server:
                server.starttls()
                server.login(self.sender_email, self.sender_password)
                server.send_message(msg)

            return {"success": True, "message": "User credentials sent successfully"}

        except smtplib.SMTPAuthenticationError as e:
            logger.error("SMTP Authentication Error: %s", str(e))
            return {"success": False, "error": f"Email authentication failed: {str(e)}"}
        except smtplib.SMTPConnectError as e:
            logger.error("SMTP Connection Error: %s", str(e))
            return {"success": False, "error": f"Cannot connect to email server: {str(e)}"}
        except Exception as e:
            logger.exception("General Error while sending credentials email: %s", str(e))
            return {"success": False, "error": str(e)}

    # ------------------- Email HTML Preparation ------------------ #
    def prepare_html_for_email(self, html_content: str, full_context: dict = None) -> str:
        """Prepare an email-safe HTML version of the invoice template.

        This function will remove scripts and add conservative inline styles suitable for email
        bodies while preserving the invoice layout.
        """
        html = html_content or ""
        html = self.sanitize_html(html)

        # Hide interactive elements
        html = html.replace('class="no-print"', 'style="display:none"')
        html = html.replace("class='no-print'", 'style="display:none"')

        # Email-specific minimal styles (kept small)
        email_styles = """
        <style>
        body { margin: 0; padding: 10px; font-size: 10px !important; }
        .invoice-box { max-width: 100%; }
        table { width: 100%; border-collapse: collapse; font-size: 10px !important; }
        th, td { font-size: 10px !important; padding: 3px !important; }
        p { font-size: 10px !important; margin: 2px 0 !important; }
        .company-info p { font-size: 10px !important; }
        .brand-name { font-size: 14px !important; }
        .brand-slogan { font-size: 9px !important; }
        small { font-size: 8px !important; }
        .amount-section { font-size: 10px !important; }
        .amount-section p { font-size: 10px !important; }
        .amount-section h2 { font-size: 16px !important; }
        </style>
        """

        if "</head>" in html.lower():
            parts = re.split(r"(</head>)", html, flags=re.IGNORECASE)
            for i, part in enumerate(parts):
                if part.lower() == "</head>":
                    parts[i] = email_styles + part
                    break
            html = "".join(parts)
        else:
            html = email_styles + html

        # Ensure payment section exists in the email view too
        html = self.insert_payment_section(html, full_context or {})

        return html
