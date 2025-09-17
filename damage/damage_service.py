from datetime import datetime
from src.extensions import db
from damage.supplier_return import SupplierReturn
from returns.product_return import DamagedProduct
from products.product import Product
from suppliers.supplier import Supplier

class DamageService:
    
    @staticmethod
    def return_to_supplier(damaged_product_id, return_type, notes=None):
        """Return damaged product to supplier"""
        try:
            # Get damaged product
            damaged_product = DamagedProduct.query.get(damaged_product_id)
            if not damaged_product:
                return {"success": False, "error": "Damaged product not found"}
            
            # Check if already returned
            if damaged_product.status == "Returned to Supplier":
                return {"success": False, "error": "Already returned to supplier"}
            
            # Find supplier from purchase history
            from stock_transactions.stock_transaction import StockTransaction
            purchase = StockTransaction.query.filter_by(
                product_id=damaged_product.product_id,
                transaction_type='Purchase'
            ).order_by(StockTransaction.transaction_date.desc()).first()
            
            if not purchase or not purchase.supplier_id:
                return {"success": False, "error": "Cannot determine supplier"}
            
            # Calculate refund amount
            refund_amount = 0
            if return_type == 'refund':
                product = Product.query.get(damaged_product.product_id)
                if product:
                    refund_amount = float(product.purchase_price or 0) * damaged_product.quantity
            
            # Create supplier return
            supplier_return = SupplierReturn(
                damaged_product_id=damaged_product_id,
                supplier_id=purchase.supplier_id,
                return_type=return_type,
                quantity_returned=damaged_product.quantity,
                refund_amount=refund_amount,
                notes=notes
            )
            
            db.session.add(supplier_return)
            
            # Update damaged product status
            damaged_product.status = "Returned to Supplier"
            damaged_product.action_taken = "Return_to_Supplier"
            damaged_product.action_date = datetime.utcnow()
            
            db.session.commit()
            
            return {
                "success": True,
                "supplier_return_id": supplier_return.id,
                "return_number": supplier_return.return_number,
                "refund_amount": refund_amount
            }
            
        except Exception as e:
            db.session.rollback()
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def get_returnable_damaged_products():
        """Get damaged products that can be returned to supplier"""
        damaged_products = DamagedProduct.query.filter(
            DamagedProduct.status.in_(['Stored', 'Repaired'])
        ).all()
        
        returnable = []
        for dp in damaged_products:
            product = Product.query.get(dp.product_id) if dp.product_id else None
            
            # Find supplier
            from stock_transactions.stock_transaction import StockTransaction
            purchase = StockTransaction.query.filter_by(
                product_id=dp.product_id,
                transaction_type='Purchase'
            ).order_by(StockTransaction.transaction_date.desc()).first()
            
            supplier = Supplier.query.get(purchase.supplier_id) if purchase else None
            
            returnable.append({
                "damaged_product_id": dp.id,
                "product": {
                    "id": product.id,
                    "name": product.product_name,
                    "sku": product.sku,
                    "purchase_price": str(product.purchase_price)
                } if product else None,
                "supplier": {
                    "id": supplier.id,
                    "name": supplier.name
                } if supplier else None,
                "quantity": dp.quantity,
                "damage_level": dp.damage_level,
                "damage_date": dp.damage_date.strftime("%Y-%m-%d"),
                "status": dp.status
            })
        
        return returnable