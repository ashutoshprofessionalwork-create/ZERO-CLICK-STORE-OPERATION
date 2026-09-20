from database.init_db import init_db
from backend import tools

def test_tools():
    init_db()
    
    print("--- 1. Testing search_product ---")
    res = tools.search_product("atta")
    print("Search 'atta':", res)
    assert len(res) >= 2
    
    print("\n--- 2. Testing check_inventory ---")
    p1 = res[0]["id"]
    inv = tools.check_inventory(p1)
    print(f"Inventory for product {p1}:", inv)
    assert inv["stock"] >= 0
    
    print("\n--- 3. Testing create_order & update_inventory ---")
    order_res = tools.create_order(
        customer_phone="+919876543210",
        items=[{"product_id": p1, "quantity": 2}],
        customer_name="Ramesh Kumar",
        address="House 12, Main Street"
    )
    print("Created Order:", order_res)
    assert order_res["status"] == "confirmed"
    
    inv_after = tools.check_inventory(p1)
    print(f"Inventory after order for product {p1}:", inv_after)
    assert inv_after["stock"] == inv["stock"] - 2
    
    print("\nAll tool tests passed!")

if __name__ == "__main__":
    test_tools()
