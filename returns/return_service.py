# services/return_service.py
from datetime import datetime
from src.extensions import db
from returns.product_return import ProductReturn, DamagedProduct
from products.product import Product
from stock_transactions.stock_transaction import StockTransaction
from sqlalchemy.exc import SQLAlchemyError

class ReturnService:
    
    @staticmethod
    def validate_payment_status(invoice):
        """Validate if returns are allowed based on payment status"""
        restricted_statuses = ['Pending', 'Partially Paid']
        if invoice.status in restricted_statuses:
            return False, f"Returns, exchanges, and replacements are not allowed when payment status is '{invoice.status}'. Please complete payment first."
        return True, None
    
    @staticmethod
    def validate_return_quantity(invoice_id, product_id, quantity_to_return):
        """Validate that customer can only return up to the quantity they purchased"""
        from invoices.invoice_item import InvoiceItem
        
        # Get original purchase quantity
        invoice_item = InvoiceItem.query.filter_by(
            invoice_id=invoice_id, 
            product_id=product_id
        ).first()
        
        if not invoice_item:
            return False, "Product not found in this invoice"
        
        purchased_quantity = invoice_item.quantity
        
        # Get total already returned quantity for this product from this invoice
        existing_returns = ProductReturn.query.filter_by(
            original_invoice_id=invoice_id,
            product_id=product_id
        ).all()
        
        total_returned = sum(r.quantity_returned for r in existing_returns)
        remaining_quantity = purchased_quantity - total_returned
        
        if quantity_to_return > remaining_quantity:
            return False, f"Cannot return {quantity_to_return} items. Only {remaining_quantity} items available for return (purchased: {purchased_quantity}, already returned: {total_returned})"
        
        return True, None
    
    @staticmethod
    def process_return(return_data):
        """Process a product return and update stock accordingly"""
        try:
            # Create return record
            product_return = ProductReturn(**return_data)
            db.session.add(product_return)
            db.session.flush()  # Get the ID
            
            # Process based on return type
            if product_return.return_type == 'return':
                ReturnService._process_refund_return(product_return)
            elif product_return.return_type == 'exchange':
                ReturnService._process_exchange(product_return)
            elif product_return.return_type == 'damage':
                ReturnService._process_damage_return(product_return)
            
            # Update return status
            product_return.status = 'Processed'
            product_return.processed_date = datetime.utcnow()
            
            db.session.commit()
            return {"success": True, "return_id": product_return.id, "return_number": product_return.return_number}
            
        except SQLAlchemyError as e:
            db.session.rollback()
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def _process_refund_return(product_return):
        """Handle return with refund - add product back to stock"""
        # Add product back to stock
        product = Product.query.get(product_return.product_id)
        product.quantity_in_stock += product_return.quantity_returned
        
        # Create stock transaction
        stock_transaction = StockTransaction(
            product_id=product_return.product_id,
            transaction_type="Return",
            quantity=product_return.quantity_returned,
            reference_number=product_return.return_number,
            notes=f"Product return - Refund: {product_return.refund_amount}"
        )
        db.session.add(stock_transaction)
    
    @staticmethod
    def _process_exchange(product_return):
        """Handle product exchange - remove old, add new product"""
        # Remove returned product from stock (if resaleable)
        if product_return.is_resaleable:
            returned_product = Product.query.get(product_return.product_id)
            returned_product.quantity_in_stock += product_return.quantity_returned
            
            # Create return stock transaction
            return_transaction = StockTransaction(
                product_id=product_return.product_id,
                transaction_type="Return",
                quantity=product_return.quantity_returned,
                reference_number=product_return.return_number,
                notes="Product exchange - returned item"
            )
            db.session.add(return_transaction)
        
        # Remove new product from stock for exchange
        if product_return.exchange_product_id:
            exchange_product = Product.query.get(product_return.exchange_product_id)
            exchange_product.quantity_in_stock -= product_return.exchange_quantity
            
            # Create exchange stock transaction
            exchange_transaction = StockTransaction(
                product_id=product_return.exchange_product_id,
                transaction_type="Sale",
                sale_type="Exchange",
                quantity=-product_return.exchange_quantity,
                reference_number=product_return.return_number,
                notes="Product exchange - new item sent"
            )
            db.session.add(exchange_transaction)
    
    @staticmethod
    def _process_damage_return(product_return):
        """Handle damaged product return - refund or replacement"""
        # Create damaged product record
        damaged_product = DamagedProduct(
            product_id=product_return.product_id,
            return_id=product_return.id,
            quantity=product_return.quantity_returned,
            damage_reason=product_return.reason,
            damage_level=product_return.damage_level,
            storage_location="DAMAGE_WAREHOUSE"
        )
        db.session.add(damaged_product)
        
        if product_return.product_type == 'refund':
            # For refund: deduct stock (returned to supplier) and process refund
            product = Product.query.get(product_return.product_id)
            product.quantity_in_stock -= product_return.quantity_returned
            
            # Create stock transaction for refund (deduction)
            stock_transaction = StockTransaction(
                product_id=product_return.product_id,
                transaction_type="Damage_Refund",
                quantity=-product_return.quantity_returned,
                reference_number=product_return.return_number,
                notes=f"Damage refund - returned to supplier. Level: {product_return.damage_level}"
            )
            db.session.add(stock_transaction)
            
            # Set status to Paid for P&L tracking
            product_return.status = 'Paid'
            
        elif product_return.product_type == 'replacement':
            # For replacement: don't affect stock, send replacement
            product = Product.query.get(product_return.product_id)
            product.quantity_in_stock -= product_return.quantity_returned
            
            # Create stock transaction for replacement
            stock_transaction = StockTransaction(
                product_id=product_return.product_id,
                transaction_type="Damage_Replacement",
                quantity=-product_return.quantity_returned,
                reference_number=product_return.return_number,
                notes=f"Damage replacement sent. Level: {product_return.damage_level}"
            )
            db.session.add(stock_transaction)
            
            # Set refund amount to 0 for replacement
            product_return.refund_amount = 0
    
    @staticmethod
    def get_return_summary():
        """Get detailed summary of all returns with customer and invoice details"""
        returns = db.session.query(ProductReturn).all()
        
        detailed_returns = []
        for return_item in returns:
            return_detail = {
                "return_id": return_item.id,
                "return_number": return_item.return_number,
                "return_type": return_item.return_type,
                "quantity_returned": return_item.quantity_returned,
                "refund_amount": float(return_item.refund_amount) if return_item.refund_amount else 0,
                "status": return_item.status,
                "return_date": return_item.return_date.strftime("%Y-%m-%d %H:%M:%S"),
                "reason": return_item.reason,
                "customer_details": {
                    "id": return_item.customer_id,
                    "name": return_item.customer.contact_person if return_item.customer else "Unknown",
                    "phone": return_item.customer.phone if return_item.customer else None,
                    "email": return_item.customer.email if return_item.customer else None
                },
                "invoice_details": {
                    "id": return_item.original_invoice_id,
                    "invoice_number": return_item.original_invoice.invoice_number if return_item.original_invoice else None,
                    "invoice_date": return_item.original_invoice.invoice_date.strftime("%Y-%m-%d") if return_item.original_invoice else None,
                    "grand_total": float(return_item.original_invoice.grand_total) if return_item.original_invoice else 0
                },
                "product_details": {
                    "id": return_item.product_id,
                    "name": return_item.product.product_name if return_item.product else "Unknown",
                    "sku": return_item.product.sku if return_item.product else None,
                    "original_price": float(return_item.original_price)
                }
            }
            detailed_returns.append(return_detail)
        
        summary = {
            "summary_statistics": {
                "total_returns": len(returns),
                "by_type": {
                    "return": len([r for r in returns if r.return_type == 'return']),
                    "exchange": len([r for r in returns if r.return_type == 'exchange']),
                    "damage": len([r for r in returns if r.return_type == 'damage'])
                },
                "total_refund_amount": float(sum([r.refund_amount for r in returns if r.refund_amount])),
                "pending_returns": len([r for r in returns if r.status == 'Pending'])
            },
            "detailed_returns": detailed_returns
        }
        
        return summary
    
    @staticmethod
    def get_damaged_products_inventory():
        """Get comprehensive inventory of damaged products with all details"""
        damaged_products = db.session.query(DamagedProduct).all()
        
        inventory = []
        total_damage_value = 0
        
        for item in damaged_products:
            # Get return details
            return_record = item.return_record if item.return_record else None
            
            # Get customer details
            customer = None
            if return_record and return_record.customer:
                customer = return_record.customer
            
            # Get invoice details
            invoice = None
            if return_record and return_record.original_invoice:
                invoice = return_record.original_invoice
            
            # Get product details with category
            product = item.product
            category = None
            if product and product.category_id:
                from category.category import Category
                category = Category.query.get(product.category_id)
            
            # Get payment details if invoice exists
            payment_details = None
            if invoice:
                from payments.payment import Payment
                payments = Payment.query.filter_by(invoice_id=invoice.id).all()
                total_paid = sum([float(p.amount_paid) for p in payments])
                payment_details = {
                    "total_invoice_amount": float(invoice.grand_total),
                    "total_paid": total_paid,
                    "pending_amount": float(invoice.grand_total) - total_paid,
                    "payment_status": "Paid" if total_paid >= float(invoice.grand_total) else "Pending"
                }
            
            # Calculate damage value
            damage_value = float(return_record.original_price) * item.quantity if return_record else 0
            total_damage_value += damage_value
            
            inventory.append({
                "damaged_product_id": item.id,
                "return_id": item.return_id,
                "return_number": return_record.return_number if return_record else None,
                "quantity_damaged": item.quantity,
                "damage_level": item.damage_level,
                "damage_reason": item.damage_reason,
                "damage_date": item.damage_date.strftime("%Y-%m-%d %H:%M:%S"),
                "storage_location": item.storage_location,
                "status": item.status,
                "action_taken": item.action_taken,
                "repair_cost": float(item.repair_cost) if item.repair_cost else 0,
                "damage_value": damage_value,
                "customer_details": {
                    "customer_id": customer.id if customer else None,
                    "customer_name": customer.contact_person if customer else None,
                    "business_name": customer.business_name if customer else None,
                    "phone": customer.phone if customer else None,
                    "email": customer.email if customer else None,
                    "address": customer.billing_address if customer else None
                } if customer else None,
                "product_details": {
                    "product_id": product.id if product else None,
                    "product_name": product.product_name if product else None,
                    "sku": product.sku if product else None,
                    "original_price": float(return_record.original_price) if return_record else 0,
                    "current_stock": product.quantity_in_stock if product else 0,
                    "category_name": category.name if category else None
                } if product else None,
                "invoice_details": {
                    "invoice_id": invoice.id if invoice else None,
                    "invoice_number": invoice.invoice_number if invoice else None,
                    "invoice_date": invoice.invoice_date.strftime("%Y-%m-%d") if invoice else None,
                    "grand_total": float(invoice.grand_total) if invoice else 0,
                    "payment_terms": invoice.payment_terms if invoice else None
                } if invoice else None,
                "payment_details": payment_details,
                "refund_details": {
                    "refund_amount": float(return_record.refund_amount) if return_record and return_record.refund_amount else 0,
                    "refund_status": return_record.status if return_record else None,
                    "return_date": return_record.return_date.strftime("%Y-%m-%d %H:%M:%S") if return_record else None
                } if return_record else None
            })
        
        # Summary statistics
        summary = {
            "total_damaged_items": len(damaged_products),
            "total_damage_value": total_damage_value,
            "by_status": {
                "stored": len([i for i in damaged_products if i.status == 'Stored']),
                "repaired": len([i for i in damaged_products if i.status == 'Repaired']),
                "disposed": len([i for i in damaged_products if i.status == 'Disposed'])
            },
            "by_damage_level": {
                "minor": len([i for i in damaged_products if i.damage_level == 'Minor']),
                "major": len([i for i in damaged_products if i.damage_level == 'Major']),
                "total": len([i for i in damaged_products if i.damage_level == 'Total'])
            }
        }
        
        return {
            "summary": summary,
            "damaged_products": inventory
        }