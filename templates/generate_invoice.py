import os
import sys
import json
import requests
from jinja2 import Environment, FileSystemLoader
import pdfkit
import webbrowser
from datetime import datetime
from flask import render_template, abort

def fetch_invoice_data(invoice_id, base_url="http://localhost:5000"):
    """
    Fetch invoice data from the API
    """
    try:
        url = f"{base_url}/payments/invoice/{invoice_id}/details"
        print(f"Fetching data from: {url}")
        
        response = requests.get(url, timeout=30)
        if response.status_code != 200:
            raise Exception(f"API returned status {response.status_code}: {response.text}")
        
        return response.json()
    except requests.exceptions.ConnectionError:
        raise Exception("Could not connect to Flask server. Make sure it's running on localhost:5000")
    except Exception as e:
        raise Exception(f"Error fetching invoice data: {str(e)}")

def generate_invoice_pdf(invoice_id):
    """
    Generate PDF invoice from API data
    """
    try:
        # Fetch invoice data from API
        print(f"Generating invoice PDF for Invoice ID: {invoice_id}")
        invoice_data = fetch_invoice_data(invoice_id)
        
        # Setup Jinja2 environment
        env = Environment(loader=FileSystemLoader('templates'))
        template = env.get_template('invoice_template.html')
        
        # Add current timestamp
        invoice_data['generated_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Render HTML
        html_content = template.render(**invoice_data)
        
        # Create output directory
        output_dir = "generated_invoices"
        os.makedirs(output_dir, exist_ok=True)
        
        # Generate filenames with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        html_filename = f"{output_dir}/invoice_{invoice_id}_{timestamp}.html"
        pdf_filename = f"{output_dir}/invoice_{invoice_id}_{timestamp}.pdf"
        
        # Save HTML file
        with open(html_filename, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"✅ HTML saved: {html_filename}")
        
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
            'load-error-handling': 'ignore'
        }
        
        # Try to generate PDF
        try:
            pdfkit.from_string(html_content, pdf_filename, options=options)
            print(f"✅ PDF saved: {pdf_filename}")
        except Exception as pdf_error:
            print(f"⚠️  PDF generation failed: {str(pdf_error)}")
            print(f"📄 HTML file created successfully: {html_filename}")
            print(f"💡 To generate PDF: Install wkhtmltopdf or open HTML in browser and print to PDF")
            
            # Open HTML in browser as fallback
            try:
                webbrowser.open(f'file://{os.path.abspath(html_filename)}')
                print(f"🌐 Opening HTML in browser...")
            except:
                pass
            
            pdf_filename = None
        
        return {
            "success": True,
            "html_file": html_filename,
            "pdf_file": pdf_filename,
            "invoice_data": invoice_data
        }
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }

def main():
    """
    Command line interface
    """
    if len(sys.argv) != 2:
        print("Usage: python generate_invoice.py <invoice_id>")
        print("Example: python generate_invoice.py 4001")
        sys.exit(1)
    
    try:
        invoice_id = int(sys.argv[1])
    except ValueError:
        print("Error: Invoice ID must be a number")
        sys.exit(1)
    
    print("=" * 50)
    print("INVOICE PDF GENERATOR")
    print("=" * 50)
    
    result = generate_invoice_pdf(invoice_id)
    
    if result["success"]:
        print("\n🎉 Invoice generated successfully!")
        print(f"📄 HTML: {result['html_file']}")
        if result['pdf_file']:
            print(f"📋 PDF: {result['pdf_file']}")
        else:
            print("📋 PDF: Not generated (wkhtmltopdf not installed)")
        print(f"💰 Total Amount: ₹{result['invoice_data']['summary']['invoice_total']}")
        print(f"👤 Customer: {result['invoice_data']['customer']['full_name']}")
        
        if not result['pdf_file']:
            print("\n💡 To install wkhtmltopdf:")
            print("   Windows: Download from https://wkhtmltopdf.org/downloads.html")
            print("   Or use the HTML file - it's print-ready!")
    else:
        print(f"\n❌ Failed to generate invoice: {result['error']}")
        sys.exit(1)

def get_invoice_with_template(invoice_id, template_name="invoice_template"):
    """
    Route handler for dynamic template selection
    """
    available_templates = [
        "invoice_template", "template1", "template2", "template3", "template4", 
        "template5", "template6", "template7", "template8", "template9", 
        "template10", "template11"
    ]
    
    if template_name not in available_templates:
        abort(404)
    
    try:
        invoice_data = fetch_invoice_data(invoice_id)
        template_path = os.path.dirname(__file__)
        env = Environment(loader=FileSystemLoader(template_path), autoescape=True)
        template = env.get_template(f'{template_name}.html')
        invoice_data['generated_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return template.render(**invoice_data)
    except Exception as e:
        return f"Error: {str(e)}", 500

# Flask route registration function
# This file is no longer needed - routes are handled in invoice_web_routes.py

if __name__ == "__main__":
    main()