from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_api_products():
    res = client.get("/api/products")
    assert res.status_code == 200
    products = res.json()
    assert isinstance(products, list)
    assert len(products) > 0
    assert "name" in products[0]

def test_api_orders():
    res = client.get("/api/orders")
    assert res.status_code == 200
    orders = res.json()
    assert isinstance(orders, list)

def test_api_stats():
    res = client.get("/api/stats")
    assert res.status_code == 200
    stats = res.json()
    assert "total_orders" in stats
    assert "total_revenue" in stats
    assert "total_products" in stats

def test_api_inventory_update():
    res = client.post("/api/inventory/update", json={"product_id": 1, "qty_delta": 2})
    assert res.status_code == 200
    data = res.json()
    assert data["product_id"] == 1

def test_create_order_and_status():
    order_payload = {
        "customer_phone": "+919876543210",
        "customer_name": "Test User",
        "address": "123 Test Street",
        "items": [{"product_id": 1, "quantity": 1}]
    }
    res = client.post("/api/orders", json=order_payload)
    assert res.status_code == 200
    order_data = res.json()
    assert "order_id" in order_data
    order_id = order_data["order_id"]

    res = client.post(f"/api/orders/{order_id}/status", json={"status": "out_for_delivery"})
    assert res.status_code == 200
    assert res.json()["status"] == "out_for_delivery"
