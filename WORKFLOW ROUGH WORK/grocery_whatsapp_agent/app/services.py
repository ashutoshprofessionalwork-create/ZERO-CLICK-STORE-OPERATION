from .models import Product, CartItem, Order, OrderItem

DELIVERY_FEE = 30.0

def seed(db):
    if db.query(Product).count():
        return
    db.add_all([
        Product(name="Rice", unit="kg", price=60, stock=50),
        Product(name="Milk", unit="litre", price=65, stock=20),
        Product(name="Maggi", unit="packet", price=15, stock=30),
    ])
    db.commit()

def summary(db, customer_id):
    items = db.query(CartItem).filter_by(customer_id=customer_id).all()
    rows, subtotal = [], 0.0
    for x in items:
        line = x.quantity * x.product.price
        subtotal += line
        rows.append({
            "product_id": x.product.id,
            "product": x.product.name,
            "quantity": x.quantity,
            "unit": x.product.unit,
            "price": x.product.price,
            "line_total": line
        })
    delivery = DELIVERY_FEE if rows else 0
    return {"items": rows, "subtotal": subtotal, "delivery": delivery,
            "total": subtotal + delivery}

def add_cart(db, customer_id, product_id, quantity):
    if quantity <= 0:
        raise ValueError("Quantity must be greater than zero.")
    p = db.get(Product, product_id)
    if not p:
        raise ValueError("Product not found.")

    item = db.query(CartItem).filter_by(
        customer_id=customer_id, product_id=product_id
    ).first()
    new_qty = quantity + (item.quantity if item else 0)

    # Only validate availability. DO NOT reduce stock.
    if new_qty > p.stock:
        raise ValueError(f"Only {p.stock:g} {p.unit} of {p.name} is available.")

    if item:
        item.quantity = new_qty
    else:
        db.add(CartItem(customer_id=customer_id, product_id=product_id,
                        quantity=quantity))
    db.commit()

def clear_cart(db, customer_id):
    db.query(CartItem).filter_by(customer_id=customer_id).delete()
    db.commit()

def confirm_order(db, customer_id):
    # THIS IS THE ONLY FUNCTION THAT CHANGES PERMANENT INVENTORY.
    items = db.query(CartItem).filter_by(customer_id=customer_id).all()
    if not items:
        raise ValueError("Your cart is empty.")

    try:
        # 1. Re-check current stock.
        for item in items:
            p = db.get(Product, item.product_id)
            if not p:
                raise ValueError("A product in your cart no longer exists.")
            if item.quantity > p.stock:
                raise ValueError(
                    f"Sorry, only {p.stock:g} {p.unit} of {p.name} is available now. "
                    f"Your cart needs {item.quantity:g}."
                )

        # 2. Re-check current prices and calculate total.
        subtotal = sum(
            item.quantity * db.get(Product, item.product_id).price
            for item in items
        )
        total = subtotal + DELIVERY_FEE

        # 3. Create order.
        order = Order(customer_id=customer_id, status="CONFIRMED", total=total)
        db.add(order)
        db.flush()

        # 4-5. Create order items and reduce inventory.
        for item in items:
            p = db.get(Product, item.product_id)
            db.add(OrderItem(
                order_id=order.id, product_id=p.id, product_name=p.name,
                unit=p.unit, quantity=item.quantity, price=p.price
            ))
            p.stock -= item.quantity

        # 6. Clear temporary cart.
        for item in items:
            db.delete(item)

        # 7. One atomic commit.
        db.commit()
        return order

    except Exception:
        db.rollback()
        raise
