from extensions import db
from purchases.purchase_damage import PurchaseDamage
from stock_transactions.stock_transaction import StockTransaction
from products.product import Product
from decimal import Decimal

class PurchaseDamageService:
    
    @staticmethod
    def create_bulk_damage_record(supplier_id, damage_type, damage_reason, notes, damaged_products):
        """
        Create damage records for multiple products
        damaged_products: [{'purchase_id': 1, 'product_id': 1, 'damaged_quantity': 5}, ...]
        """
        damage_records = []
        total_refund = Decimal('0')
        
        try:
            for item in damaged_products:
                purchase_id = item['purchase_id']
                product_id = item['product_id']
                damaged_quantity = item['damaged_quantity']
                
                # Validate purchase exists
                purchase = StockTransaction.query.get(purchase_id)
                if not purchase or purchase.transaction_type != 'Purchase':
                    raise ValueError(f"Invalid purchase ID: {purchase_id}")
                
                # Validate product exists
                product = Product.query.get(product_id)
                if not product:
                    raise ValueError(f"Product not found: {product_id}")
                
                # Validate damaged quantity doesn't exceed purchased quantity
                if damaged_quantity > purchase.quantity:
                    raise ValueError(f"Damaged quantity {damaged_quantity} exceeds purchased quantity {purchase.quantity} for product {product.product_name}")
                
                # Calculate refund amount using purchase price
                refund_amount = None
                if damage_type == 'refund':
                    refund_amount = Decimal(str(product.purchase_price)) * Decimal(str(damaged_quantity))
                    total_refund += refund_amount
                    
                    # Reduce product stock for refund
                    if product.stock_quantity >= damaged_quantity:
                        product.stock_quantity -= damaged_quantity
                    else:
                        raise ValueError(f"Insufficient stock to process refund for {product.product_name}")
                
                # Create damage record
                damage_record = PurchaseDamage(
                    purchase_id=purchase_id,
                    product_id=product_id,
                    supplier_id=supplier_id,
                    damaged_quantity=damaged_quantity,
                    damage_type=damage_type,
                    damage_reason=damage_reason,
                    refund_amount=refund_amount,
                    notes=notes
                )
                
                db.session.add(damage_record)
                damage_records.append({
                    "product_name": product.product_name,
                    "damaged_quantity": damaged_quantity,
                    "refund_amount": float(refund_amount) if refund_amount else None
                })
            
            db.session.commit()
            
            return {
                "supplier_id": supplier_id,
                "damage_type": damage_type,
                "total_products": len(damaged_products),
                "total_refund_amount": float(total_refund),
                "damaged_products": damage_records,
                "stock_updated": damage_type == 'refund'
            }
            
        except Exception as e:
            db.session.rollback()
            raise e
    
    @staticmethod
    def get_damage_records(supplier_id=None):
        query = PurchaseDamage.query
        if supplier_id:
            query = query.filter_by(supplier_id=supplier_id)
        
        damages = query.all()
        result = []
        
        for damage in damages:
            result.append({
                "damage_id": damage.id,
                "purchase_id": damage.purchase_id,
                "product_name": damage.product.product_name,
                "supplier_name": damage.supplier.name,
                "damaged_quantity": damage.damaged_quantity,
                "damage_type": damage.damage_type,
                "damage_reason": damage.damage_reason,
                "refund_amount": float(damage.refund_amount) if damage.refund_amount else None,
                "status": damage.status,
                "damage_date": damage.damage_date.isoformat(),
                "notes": damage.notes
            })
        
        return result