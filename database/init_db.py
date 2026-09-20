import sqlite3
import os

# Point database to root directory or relative path
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "store.db")

def init_db(db_path: str = DB_PATH):
    if os.path.exists(db_path):
        os.remove(db_path)
        print(f"Removed existing database at {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create tables based on schema
    cursor.execute("""
    CREATE TABLE products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        price REAL NOT NULL,
        stock INTEGER NOT NULL,
        low_stock_threshold INTEGER DEFAULT 5
    );
    """)

    cursor.execute("""
    CREATE TABLE customers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        phone TEXT UNIQUE,
        name TEXT,
        address TEXT
    );
    """)

    cursor.execute("""
    CREATE TABLE orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER,
        total REAL,
        status TEXT DEFAULT 'confirmed',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (customer_id) REFERENCES customers(id)
    );
    """)

    cursor.execute("""
    CREATE TABLE order_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER,
        product_id INTEGER,
        quantity INTEGER,
        unit_price REAL,
        FOREIGN KEY (order_id) REFERENCES orders(id),
        FOREIGN KEY (product_id) REFERENCES products(id)
    );
    """)

    # Seed data
    products = [
        ("Aashirvaad Atta 5kg", 260.0, 15, 5),
        ("Fortune Sunlite Sunflower Oil 1L", 145.0, 10, 3),
        ("Maggi 2-Minute Noodles 70g", 14.0, 50, 10),
        ("Amul Butter 100g", 56.0, 8, 3),
        ("Amul Taaza Milk 500ml", 27.0, 20, 5),
        ("Tata Salt 1kg", 28.0, 30, 5),
        ("Surf Excel Easy Wash Powder 1kg", 140.0, 12, 3),
        ("Taj Mahal Tea 250g", 180.0, 6, 2),
        ("Good Day Cashew Biscuits 100g", 30.0, 25, 5),
        ("Dettol Original Soap 125g", 45.0, 15, 4),
        # Low stock item for testing out-of-stock / alternates logic
        ("Aashirvaad Atta 10kg", 490.0, 1, 2),
        ("Fortune Mustard Oil 1L", 160.0, 0, 3)
    ]

    cursor.executemany("""
    INSERT INTO products (name, price, stock, low_stock_threshold)
    VALUES (?, ?, ?, ?);
    """, products)

    conn.commit()
    conn.close()
    print(f"Database initialized and seeded successfully at {db_path}")

if __name__ == "__main__":
    init_db()
