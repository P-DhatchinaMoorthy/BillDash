from src.extensions import db
from products.product import Product
from suppliers.supplier import Supplier

class ProductService:
    @staticmethod
    def create_product(data):
        """
        Create product. purchase_price must be present.
        selling_price is auto-calculated via model event.
        """
        # Check if product with this ID already exists
        existing_product = Product.query.get(data["id"])
        if existing_product:
            return existing_product, True  # Return existing product and flag
        
        product = Product(
            id=data["id"],
            product_name=data["product_name"],
            description=data.get("description"),
            sku=data["sku"],
            category_id=data.get("category_id"),
            subcategory_id=data.get("subcategory_id"),
            unit_of_measure=data.get("unit_of_measure"),
            purchase_price=data.get("purchase_price", 0),
            quantity_in_stock=data.get("quantity_in_stock", 0),
            reorder_level=data.get("reorder_level"),
            max_stock_level=data.get("max_stock_level"),
            supplier_id=data.get("supplier_id"),
            batch_number=data.get("batch_number"),
            expiry_date=data.get("expiry_date"),
            barcode=data.get("barcode"),

        )
        db.session.add(product)
        db.session.commit()
        return product, False  # Return new product and flag

    @staticmethod
    def get_product_by_id(product_id):
        return Product.query.get(product_id)
