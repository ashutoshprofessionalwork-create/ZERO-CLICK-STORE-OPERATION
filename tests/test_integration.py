import unittest
from database.init_db import init_db
from ai.agent import run_agent_loop
from backend import tools

class TestMemberABackend(unittest.TestCase):
    def setUp(self):
        init_db()

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

if __name__ == "__main__":
    unittest.main()
