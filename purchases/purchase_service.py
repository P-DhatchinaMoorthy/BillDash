# services/purchase_service.py
from decimal import Decimal
from src.extensions import db
from products.product import Product
from stock_transactions.stock_transaction import StockTransaction
from datetime import datetime


class PurchaseService:
    @staticmethod
    def add_multiple_stock_from_supplier(products, supplier_id, reference_number=None, notes=None,
                                         total_amount=None, payment_amount=0, payment_method=None,
                                         transaction_reference=None):
        """
        Add stock for multiple products from supplier in a single purchase.
        """
        if not products or len(products) == 0:
            raise ValueError("Products list cannot be empty")

        # Generate base purchase ID starting from 5001
        last_transaction = StockTransaction.query.filter_by(transaction_type="Purchase").order_by(
            StockTransaction.id.desc()).first()
        base_purchase_id = 5001 if not last_transaction else max(5001, (last_transaction.id or 0) + 1)

        # Calculate total amount if not provided
        calculated_total = Decimal('0')
        product_details = []

        # Create one purchase record with multiple items
        purchase_items = []

        for product_data in products:
            product_id = product_data.get("product_id")
            quantity = product_data.get("quantity")

            if not product_id or not quantity:
                raise ValueError("Each product must have product_id and quantity")

            product = Product.query.get(product_id)
            if not product:
                raise ValueError(f"Product {product_id} not found")

            # Update product quantity
            product.quantity_in_stock += quantity

            # Calculate amount for this product
            product_amount = Decimal(product.purchase_price) * quantity
            calculated_total += product_amount

            purchase_items.append({
                "product_id": product_id,
                "quantity": quantity,
                "product": product,
                "amount": product_amount
            })

            product_details.append({
                "product_id": product.id,
                "name": product.product_name,
                "sku": product.sku,
                "quantity_added": quantity,
                "purchase_price": str(product.purchase_price),
                "amount": str(product_amount),
                "new_stock": product.quantity_in_stock
            })

        # Create one main purchase transaction record
        main_transaction = StockTransaction(
            id=base_purchase_id,
            product_id=purchase_items[0]["product_id"],  # Use first product as main
            transaction_type="Purchase",
            quantity=sum(item["quantity"] for item in purchase_items),  # Total quantity
            supplier_id=supplier_id,
            reference_number=reference_number,
            notes=notes
        )
        db.session.add(main_transaction)

        # Use provided total or calculated total
        total_amt = Decimal(total_amount) if total_amount else calculated_total
        paid_amt = Decimal(payment_amount)

        # Calculate payment status
        if paid_amt >= total_amt:
            payment_status = "Paid"
        elif paid_amt > 0:
            payment_status = "Partially Paid"
        else:
            payment_status = "Pending"

        # Store payment info and product details in transaction notes
        import json
        payment_info = {
            "payment_amount": str(paid_amt),
            "payment_method": payment_method,
            "payment_status": payment_status,
            "transaction_reference": transaction_reference,
            "total_amount": str(total_amt),
            "products": product_details,
            "created_at": datetime.now().isoformat()
        }
        main_transaction.notes = json.dumps(payment_info)

        # Get supplier details
        from suppliers.supplier import Supplier
        supplier = Supplier.query.get(supplier_id)

        db.session.commit()

        balance_due = max(Decimal('0'), total_amt - paid_amt)  # Prevent negative balance

        return {
            "purchase_id": base_purchase_id,
            "payment_details": {
                "total_amount": f"{total_amt:.2f}",
                "payment_amount": f"{paid_amt:.2f}",
                "payment_method": payment_method,
                "payment_status": payment_status,
                "transaction_reference": transaction_reference,
                "balance_due": f"{balance_due:.2f}"
            },
            "products": product_details,
            "supplier_details": {
                "id": supplier.id,
                "name": supplier.name,
                "contact_person": supplier.contact_person,
                "phone": supplier.phone
            } if supplier else None,
            "purchase_summary": {
                "total_products": len(products),
                "total_quantity": sum(p.get("quantity", 0) for p in products),
                "reference_number": reference_number,
                "notes": notes
            }
        }

    @staticmethod
    def add_stock_from_supplier(product_id, quantity, supplier_id, purchase_price=None, reference_number=None,
                                notes=None,
                                total_amount=None, payment_amount=0, payment_method=None, transaction_reference=None):
        """
        Add stock from supplier and update product quantity.
        """
        product = Product.query.get(product_id)
        if not product:
            raise ValueError("Product not found")

        # Update product quantity
        product.quantity_in_stock += quantity

        # Update purchase price if provided
        if purchase_price:
            product.purchase_price = Decimal(purchase_price)

        # Generate purchase ID starting from 5001
        last_transaction = StockTransaction.query.filter_by(transaction_type="Purchase").order_by(
            StockTransaction.id.desc()).first()
        purchase_id = 5001 if not last_transaction else max(5001, (last_transaction.id or 0) + 1)

        # Calculate payment status
        total_amt = Decimal(total_amount) if total_amount else Decimal(purchase_price or 0) * quantity
        paid_amt = Decimal(payment_amount)

        if paid_amt >= total_amt:
            payment_status = "Paid"
        elif paid_amt > 0:
            payment_status = "Partially Paid"
        else:
            payment_status = "Pending"

        # Create stock transaction record
        stock_transaction = StockTransaction(
            id=purchase_id,
            product_id=product_id,
            transaction_type="Purchase",
            quantity=quantity,
            supplier_id=supplier_id,
            reference_number=reference_number,
            notes=notes
        )

        db.session.add(stock_transaction)
        db.session.flush()  # Get the ID

        # Get comprehensive details
        from suppliers.supplier import Supplier
        from category.category import Category

        supplier = Supplier.query.get(supplier_id)
        category = Category.query.get(product.category_id) if product.category_id else None

        db.session.commit()

        balance_due = max(Decimal('0'), total_amt - paid_amt)  # Prevent negative balance

        return {
            "purchase_id": purchase_id,
            "transaction_id": stock_transaction.id,
            "payment_details": {
                "total_amount": f"{total_amt:.2f}",
                "payment_amount": f"{paid_amt:.2f}",
                "payment_method": payment_method,
                "payment_status": payment_status,
                "transaction_reference": transaction_reference,
                "balance_due": f"{balance_due:.2f}"
            },
            "product_details": {
                "id": product.id,
                "name": product.product_name,
                "sku": product.sku,
                "purchase_price": str(product.purchase_price),
                "quantity_in_stock": product.quantity_in_stock
            },
            "supplier_details": {
                "id": supplier.id,
                "name": supplier.name,
                "contact_person": supplier.contact_person,
                "phone": supplier.phone
            } if supplier else None,
            "stock_transaction": {
                "id": stock_transaction.id,
                "quantity_added": quantity,
                "transaction_date": stock_transaction.transaction_date.isoformat()
            }
        }

    @staticmethod
    def update_payment(purchase_id, payment_amount, payment_method=None, transaction_reference=None):
        """
        Update payment for existing purchase - adds to existing payment amount
        """
        transaction = StockTransaction.query.get(purchase_id)
        if not transaction or transaction.transaction_type != "Purchase":
            raise ValueError("Purchase not found")

        # Only use the specific transaction for this purchase ID
        related_transactions = [transaction]

        # Get total amount from stored payment info (original purchase amount)
        total_amt = Decimal('0')
        if transaction.notes:
            try:
                import json
                payment_info = json.loads(transaction.notes)
                total_amt = Decimal(payment_info.get("total_amount", "0"))
            except json.JSONDecodeError:
                pass

        # Fallback: calculate from current product prices if no stored amount
        if total_amt == 0:
            product_groups = {}
            for trans in related_transactions:
                product_id = trans.product_id
                if product_id in product_groups:
                    product_groups[product_id]['quantity'] += trans.quantity
                else:
                    product_groups[product_id] = {
                        'quantity': trans.quantity
                    }

            for product_id, group_data in product_groups.items():
                product = Product.query.get(product_id)
                total_qty = group_data['quantity']
                product_amount = Decimal(str(product.purchase_price)) * Decimal(str(total_qty))
                total_amt += product_amount

        # Get existing payment amount from the same stored info
        existing_paid_amt = Decimal("0")
        if transaction.notes:
            try:
                import json
                existing_payment = json.loads(transaction.notes)
                existing_paid_amt = Decimal(existing_payment.get("payment_amount", "0"))
            except json.JSONDecodeError:
                pass

        # Check if already fully paid (balance <= 0.01 to handle precision)
        current_balance = total_amt - existing_paid_amt
        if current_balance <= Decimal('0.01'):
            raise ValueError("Cannot update payment - purchase is already fully paid")

        # Add new payment to existing amount
        new_payment_amt = Decimal(payment_amount)
        total_paid_amt = existing_paid_amt + new_payment_amt

        # Prevent overpayment - cap at total amount
        if total_paid_amt > total_amt:
            total_paid_amt = total_amt

        # Calculate balance and status
        balance_amt = total_amt - total_paid_amt
        if balance_amt <= Decimal('0.01'):  # Handle floating point precision
            payment_status = "Paid"
        elif total_paid_amt > 0:
            payment_status = "Partially Paid"
        else:
            payment_status = "Pending"

        # Store payment info in notes
        payment_info = {
            "payment_amount": str(total_paid_amt),
            "payment_method": payment_method,
            "payment_status": payment_status,
            "transaction_reference": transaction_reference,
            "total_amount": str(total_amt),
            "updated_at": datetime.now().isoformat()
        }

        import json
        transaction.notes = json.dumps(payment_info)
        db.session.commit()

        balance_due = max(Decimal('0'), balance_amt)  # Prevent negative balance

        return {
            "purchase_id": purchase_id,
            "payment_details": {
                "total_amount": f"{total_amt:.2f}",
                "payment_amount": f"{total_paid_amt:.2f}",
                "payment_method": payment_method,
                "payment_status": payment_status,
                "transaction_reference": transaction_reference,
                "balance_due": f"{balance_due:.2f}"
            }
        }

    @staticmethod
    def get_purchase_details(purchase_id):
        """
        Get complete purchase details by ID including all products from same purchase
        """
        transaction = StockTransaction.query.get(purchase_id)
        if not transaction:
            # Debug: Check what purchase transactions exist
            existing_purchases = StockTransaction.query.filter_by(transaction_type="Purchase").all()
            print(f"Available purchase IDs: {[t.id for t in existing_purchases]}")
            return None
        if transaction.transaction_type != "Purchase":
            return None

        # Get related data
        from suppliers.supplier import Supplier
        from category.category import Category
        import json

        supplier = Supplier.query.get(transaction.supplier_id)

        # Get payment info from notes
        payment_info = {}
        if transaction.notes:
            try:
                payment_info = json.loads(transaction.notes)
            except:
                pass

        # Use stored product details from notes if available
        products_details = []
        if payment_info.get("products"):
            for stored_product in payment_info["products"]:
                product = Product.query.get(stored_product["product_id"])
                category = Category.query.get(product.category_id) if product and product.category_id else None

                products_details.append({
                    "transaction_id": transaction.id,
                    "product_details": {
                        "product_id": stored_product["product_id"],
                        "id": stored_product["product_id"],
                        "name": stored_product["name"],
                        "sku": stored_product["sku"],
                        "description": product.description if product else None,
                        "purchase_price": stored_product["purchase_price"],
                        "unit_of_measure": product.unit_of_measure if product else None,
                        "barcode": product.barcode if product else None,
                        "batch_number": product.batch_number if product else None,
                        "category_id": product.category_id if product else None,
                        "subcategory_id": product.subcategory_id if product else None
                    },
                    "category_details": {
                        "id": category.id,
                        "name": category.name,
                        "description": category.description
                    } if category else None,
                    "subcategory_details": {
                        "id": product.subcategory_id if product else None,
                        "name": category.subcategory_name if category else None,
                        "description": None
                    } if product and product.subcategory_id else None,
                    "purchase_details": {
                        "quantity_purchased": stored_product["quantity_added"],
                        "product_amount": stored_product["amount"],
                        "purchase_date": transaction.transaction_date.isoformat()
                    },
                    "stock_summary": {
                        "previous_stock": stored_product["new_stock"] - stored_product["quantity_added"],
                        "added_quantity": stored_product["quantity_added"],
                        "new_stock_quantity": stored_product["new_stock"],
                        "reorder_level": product.reorder_level if product else None,
                        "max_stock_level": product.max_stock_level if product else None
                    }
                })
        else:
            # Fallback to single product from transaction
            product = Product.query.get(transaction.product_id)
            category = Category.query.get(product.category_id) if product.category_id else None

            products_details.append({
                "transaction_id": transaction.id,
                "product_details": {
                    "product_id": product.id,
                    "id": product.id,
                    "name": product.product_name,
                    "sku": product.sku,
                    "description": product.description,
                    "purchase_price": str(product.purchase_price),
                    "unit_of_measure": product.unit_of_measure,
                    "barcode": product.barcode,
                    "batch_number": product.batch_number,
                    "category_id": product.category_id,
                    "subcategory_id": product.subcategory_id
                },
                "purchase_details": {
                    "quantity_purchased": transaction.quantity,
                    "product_amount": str(Decimal(product.purchase_price) * transaction.quantity),
                    "purchase_date": transaction.transaction_date.isoformat()
                }
            })

        paid_amt = Decimal(payment_info.get("payment_amount", "0"))
        payment_method = payment_info.get("payment_method")
        transaction_reference = payment_info.get("transaction_reference")
        total_purchase_amount = Decimal(payment_info.get("total_amount", "0"))

        balance_amt = total_purchase_amount - paid_amt
        payment_status = payment_info.get("payment_status", "Pending")

        # Get first product for template compatibility
        first_product = products_details[0] if products_details else {}

        return {
            "purchase_id": purchase_id,
            "reference_number": transaction.reference_number,
            "payment_details": {
                "grand_total": f"{total_purchase_amount:.2f}",
                "payment_amount": f"{paid_amt:.2f}",
                "balance_amount": f"{max(Decimal('0'), balance_amt):.2f}",
                "payment_method": payment_method,
                "payment_status": payment_status,
                "transaction_reference": transaction_reference
            },
            "supplier_details": {
                "supplier_id": supplier.id,
                "id": supplier.id,
                "name": supplier.name,
                "contact_person": supplier.contact_person,
                "email": supplier.email,
                "phone": supplier.phone,
                "address": supplier.address,
                "gst_number": supplier.gst_number,
                "payment_terms": supplier.payment_terms
            } if supplier else None,
            "purchase_details": {
                "reference_number": transaction.reference_number,
                "purchase_date": transaction.transaction_date.isoformat(),
                "quantity_purchased": first_product.get("purchase_details", {}).get("quantity_purchased", 0)
            },
            "product_details": first_product.get("product_details", {}),
            "stock_transaction": {
                "notes": transaction.notes
            },
            "purchase_summary": {
                "total_products": len(products_details),
                "total_quantity": sum(int(p["purchase_details"]["quantity_purchased"]) for p in products_details),
                "purchase_date": transaction.transaction_date.isoformat(),
                "notes": transaction.notes
            },
            "products": products_details
        }