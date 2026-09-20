import sqlite3
import os
from typing import List, Dict, Any, Optional

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "store.db")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def search_product(query: str) -> List[Dict[str, Any]]:
    """Search for products by name using fuzzy matching / LIKE query."""
    conn = get_db_connection()
    cursor = conn.cursor()
    search_term = f"%{query}%"
    cursor.execute(
        "SELECT id, name, price, stock, low_stock_threshold FROM products WHERE name LIKE ?",
        (search_term,)
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def check_inventory(product_id: int) -> Dict[str, Any]:
    """Check stock and price for a specific product by ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, name, price, stock, low_stock_threshold FROM products WHERE id = ?",
        (product_id,)
    )
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return {"error": f"Product with ID {product_id} not found."}
    
    return dict(row)

def update_inventory(product_id: int, qty_delta: int) -> Dict[str, Any]:
    """Update stock for a product. qty_delta is negative for deducting stock (orders)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT stock, low_stock_threshold, name FROM products WHERE id = ?", (product_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return {"error": f"Product with ID {product_id} not found."}
    
    current_stock = row["stock"]
    new_stock = current_stock + qty_delta
    
    if new_stock < 0:
        conn.close()
        return {"error": f"Insufficient stock for product ID {product_id}. Current stock: {current_stock}"}
    
    cursor.execute(
        "UPDATE products SET stock = ? WHERE id = ?",
        (new_stock, product_id)
    )
    conn.commit()
    
    is_low_stock = new_stock <= row["low_stock_threshold"]
    conn.close()
    
    return {
        "product_id": product_id,
        "name": row["name"],
        "new_stock": new_stock,
        "is_low_stock": is_low_stock
    }

def create_order(customer_phone: str, items: List[Dict[str, int]], customer_name: Optional[str] = None, address: Optional[str] = None) -> Dict[str, Any]:
    """
    Create a new order for a customer and record items.
    `items` should be a list of dicts: [{"product_id": int, "quantity": int}]
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get or create customer
    cursor.execute("SELECT id FROM customers WHERE phone = ?", (customer_phone,))
    cust_row = cursor.fetchone()
    
    if cust_row:
        customer_id = cust_row["id"]
        if customer_name or address:
            cursor.execute(
                "UPDATE customers SET name = COALESCE(?, name), address = COALESCE(?, address) WHERE id = ?",
                (customer_name, address, customer_id)
            )
    else:
        cursor.execute(
            "INSERT INTO customers (phone, name, address) VALUES (?, ?, ?)",
            (customer_phone, customer_name or "Guest Customer", address or "")
        )
        customer_id = cursor.lastrowid

    total_amount = 0.0
    item_details = []
    
    for item in items:
        p_id = item["product_id"]
        qty = item["quantity"]
        
        cursor.execute("SELECT name, price, stock FROM products WHERE id = ?", (p_id,))
        p_row = cursor.fetchone()
        if not p_row:
            conn.close()
            return {"error": f"Product ID {p_id} not found."}
        
        if p_row["stock"] < qty:
            conn.close()
            return {"error": f"Cannot create order: insufficient stock for '{p_row['name']}'. Requested: {qty}, Available: {p_row['stock']}"}
        
        unit_price = p_row["price"]
        item_total = unit_price * qty
        total_amount += item_total
        item_details.append({
            "product_id": p_id,
            "name": p_row["name"],
            "quantity": qty,
            "unit_price": unit_price,
            "item_total": item_total
        })

    cursor.execute(
        "INSERT INTO orders (customer_id, total, status) VALUES (?, ?, 'confirmed')",
        (customer_id, total_amount)
    )
    order_id = cursor.lastrowid

    for item in item_details:
        cursor.execute(
            "INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES (?, ?, ?, ?)",
            (order_id, item["product_id"], item["quantity"], item["unit_price"])
        )
        cursor.execute(
            "UPDATE products SET stock = stock - ? WHERE id = ?",
            (item["quantity"], item["product_id"])
        )

    conn.commit()
    conn.close()

    return {
        "order_id": order_id,
        "customer_phone": customer_phone,
        "items": item_details,
        "total_amount": total_amount,
        "status": "confirmed"
    }
