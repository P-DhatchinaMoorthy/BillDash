from decimal import Decimal
from extensions import db
from suppliers.supplier import Supplier
from purchases.purchase_bill import PurchaseBill
from datetime import datetime


class PurchaseBillingService:
    @staticmethod
    def create_purchase_bill_with_payment(supplier_id, supplier_name, contact_person, email, phone, address, gst_number,
                                          payment_amount, payment_method, bank_details=None, transaction_reference=None,
                                          notes=None):
        """
        Create or update supplier and process purchase bill payment.
        Supplier ID can be reused in purchase bills but must be unique in suppliers table.
        """
        # Get or create/update supplier
        supplier = Supplier.query.get(supplier_id)
        if not supplier:
            # Check if supplier_id already exists (should not happen with auto-increment)
            existing = Supplier.query.filter_by(id=supplier_id).first()
            if existing:
                raise ValueError(f"Supplier ID {supplier_id} already exists")

            supplier = Supplier(
                id=supplier_id,
                name=supplier_name,
                contact_person=contact_person,
                email=email,
                phone=phone,
                address=address,
                gst_number=gst_number
            )
            db.session.add(supplier)
        else:
            # Update existing supplier details
            supplier.name = supplier_name
            supplier.contact_person = contact_person
            supplier.email = email
            supplier.phone = phone
            supplier.address = address
            supplier.gst_number = gst_number

        # Create purchase bill
        bill_number = f"PB-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        purchase_bill = PurchaseBill(
            bill_number=bill_number,
            supplier_id=supplier_id,
            total_amount=Decimal(payment_amount),
            payment_amount=Decimal(payment_amount),
            payment_method=payment_method,
            payment_status="Paid",
            transaction_reference=transaction_reference,
            bank_details=bank_details,
            notes=notes
        )

        db.session.add(purchase_bill)
        db.session.commit()

        return {
            "purchase_bill_id": purchase_bill.id,
            "bill_number": purchase_bill.bill_number,
            "supplier_id": supplier_id,
            "supplier_name": supplier.name,
            "payment_amount": str(purchase_bill.payment_amount),
            "payment_status": purchase_bill.payment_status,
            "payment_date": purchase_bill.payment_date.isoformat()
        }

    @staticmethod
    def get_purchase_bill_details(bill_id):
        """
        Get detailed purchase bill information.
        """
        bill = PurchaseBill.query.get(bill_id)
        if not bill:
            return None

        supplier = Supplier.query.get(bill.supplier_id)

        return {
            "purchase_bill": {
                "id": bill.id,
                "bill_number": bill.bill_number,
                "bill_date": bill.bill_date.isoformat(),
                "due_date": bill.due_date.isoformat() if bill.due_date else None,
                "total_amount": str(bill.total_amount),
                "payment_amount": str(bill.payment_amount),
                "balance_amount": str(bill.balance_amount),
                "payment_method": bill.payment_method,
                "payment_status": bill.payment_status,
                "payment_date": bill.payment_date.isoformat(),
                "transaction_reference": bill.transaction_reference,
                "bank_details": bill.bank_details,
                "notes": bill.notes,
                "created_at": bill.created_at.isoformat()
            },
            "supplier": {
                "id": supplier.id,
                "name": supplier.name,
                "contact_person": supplier.contact_person,
                "email": supplier.email,
                "phone": supplier.phone,
                "alternate_phone": supplier.alternate_phone,
                "address": supplier.address,
                "gst_number": supplier.gst_number,
                "bank_details": supplier.bank_details,
                "payment_terms": supplier.payment_terms,
                "notes": supplier.notes
            }
        }