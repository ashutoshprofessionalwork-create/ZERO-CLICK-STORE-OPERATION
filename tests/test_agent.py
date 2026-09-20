from database.init_db import init_db
from ai.agent import run_agent_loop
from backend import tools

def test_agent_loop():
    init_db()
    print("--- Testing Agent Loop (Offline / Online) ---")
    
    test_phone = "+919999888877"
    test_msg = "Bhaiya, 2 packets Aashirvaad atta, 1 Fortune oil and 3 Maggi bhej do. Ghar pe deliver kar dena."
    
    response = run_agent_loop(customer_phone=test_phone, user_message=test_msg)
    print("Agent Response:\n")
    print(response)
    print("\n--- Agent Loop Test Completed ---")

if __name__ == "__main__":
    test_agent_loop()
