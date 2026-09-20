import unittest
from fastapi.testclient import TestClient
from database.init_db import init_db
from ai.agent import run_agent_loop
from backend import tools
from main import app

class TestMemberABackend(unittest.TestCase):
    def setUp(self):
        init_db()
        self.client = TestClient(app)

    def test_search_and_inventory(self):
        results = tools.search_product("maggi")
        self.assertTrue(len(results) > 0)
        p_id = results[0]["id"]
        inv = tools.check_inventory(p_id)
        self.assertEqual(inv["id"], p_id)

    def test_create_order_and_inventory_deduction(self):
        p = tools.search_product("salt")[0]
        initial_stock = p["stock"]
        
        order = tools.create_order(
            customer_phone="+919999000011",
            items=[{"product_id": p["id"], "quantity": 2}]
        )
        self.assertEqual(order["status"], "confirmed")
        self.assertEqual(order["total_amount"], p["price"] * 2)
        
        inv_after = tools.check_inventory(p["id"])
        self.assertEqual(inv_after["stock"], initial_stock - 2)

    def test_agent_loop_out_of_stock_alternate(self):
        reply = run_agent_loop("+919999000022", "Bhaiya 1 Fortune Mustard Oil bhej do")
        self.assertIn("out of stock", reply.lower())

    def test_rest_api_endpoints(self):
        # Search API
        res = self.client.get("/api/products/search?q=atta")
        self.assertEqual(res.status_code, 200)
        self.assertIn("products", res.json())
        self.assertTrue(len(res.json()["products"]) > 0)

        # Get product API
        prod_id = res.json()["products"][0]["id"]
        res_p = self.client.get(f"/api/products/{prod_id}")
        self.assertEqual(res_p.status_code, 200)
        self.assertEqual(res_p.json()["id"], prod_id)

        # Create Order API
        order_payload = {
            "customer_phone": "+919876543210",
            "items": [{"product_id": prod_id, "quantity": 1}]
        }
        res_o = self.client.post("/api/orders", json=order_payload)
        self.assertEqual(res_o.status_code, 200)
        self.assertEqual(res_o.json()["status"], "confirmed")
        self.assertIn("order_id", res_o.json())

    def test_mounted_phonecall_app(self):
        # Health check on subapp
        res_h = self.client.get("/phone/")
        self.assertEqual(res_h.status_code, 200)
        self.assertEqual(res_h.json()["status"], "online")

        # TwiML incoming call on mounted subapp preserves root_path in action URL
        res_v = self.client.post("/phone/voice", data={"CallSid": "CALL_TEST_MOUNT", "From": "+919876543210"})
        self.assertEqual(res_v.status_code, 200)
        self.assertIn('action="/phone/process-speech"', res_v.text)

if __name__ == "__main__":
    unittest.main()

