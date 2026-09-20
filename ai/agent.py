import json
import os
from typing import List, Dict, Any
from dotenv import load_dotenv

from backend import tools

load_dotenv()

TOOL_SCHEMAS = [
    {
        "name": "search_product",
        "description": "Search for products in the store database by name or keywords (e.g. 'atta', 'oil', 'maggi'). Returns matching products with product_id, name, price, stock.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Product search query or name keyword"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "check_inventory",
        "description": "Check current available stock and price for a specific product using its product_id.",
        "input_schema": {
            "type": "object",
            "properties": {
                "product_id": {
                    "type": "integer",
                    "description": "The unique product ID"
                }
            },
            "required": ["product_id"]
        }
    },
    {
        "name": "update_inventory",
        "description": "Manually update stock level for a product. Use negative qty_delta for reducing stock.",
        "input_schema": {
            "type": "object",
            "properties": {
                "product_id": {
                    "type": "integer",
                    "description": "Product ID to update"
                },
                "qty_delta": {
                    "type": "integer",
                    "description": "Quantity change (e.g., -2 to deduct 2 items)"
                }
            },
            "required": ["product_id", "qty_delta"]
        }
    },
    {
        "name": "create_order",
        "description": "Create a new confirmed order in the database and automatically deduct stock. ONLY call this when items are confirmed and in stock.",
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_phone": {
                    "type": "string",
                    "description": "Customer phone number"
                },
                "items": {
                    "type": "array",
                    "description": "List of order items",
                    "items": {
                        "type": "object",
                        "properties": {
                            "product_id": {"type": "integer"},
                            "quantity": {"type": "integer"}
                        },
                        "required": ["product_id", "quantity"]
                    }
                },
                "customer_name": {
                    "type": "string",
                    "description": "Customer name if known"
                },
                "address": {
                    "type": "string",
                    "description": "Delivery address if provided"
                }
            },
            "required": ["customer_phone", "items"]
        }
    }
]

SYSTEM_PROMPT = """You are an autonomous AI Kirana/General Store Operator assistant.
Your goal is to handle customer orders over WhatsApp/Voice naturally, efficiently, and accurately.

Key Persona & Tone:
- Friendly, helpful Kirana shopkeeper persona ("Bhaiya").
- Support Hinglish natively (mirror the customer's language mix: Hindi/English).

Rules & Agent Behavior:
1. When a customer asks for items, ALWAYS search the store inventory first using `search_product`.
2. Check available stock for the items.
3. Out-Of-Stock / Low-Stock Rule:
   - If an item requested is OUT OF STOCK or available in LESS quantity than requested:
     a) Do NOT create an order for that item immediately.
     b) Search for an alternate size/brand or offer partial available stock.
     c) Inform the customer clearly and ask for confirmation before adding substitutes.
4. When items are in stock and customer intent to order is clear:
   - Calculate item prices and total.
   - Call `create_order` with customer phone number and the list of item product_ids and quantities.
5. Confirmation:
   - Always reply with a summary of the order (items, quantities, unit prices, total amount) and state that the order is confirmed for delivery.
   - Keep responses concise, clear, and friendly.
"""

def execute_tool(tool_name: str, tool_args: Dict[str, Any], source: str = "web") -> Any:
    """Execute python function based on tool name from LLM."""
    if tool_name == "search_product":
        return tools.search_product(tool_args.get("query", ""))
    elif tool_name == "check_inventory":
        return tools.check_inventory(tool_args.get("product_id"))
    elif tool_name == "update_inventory":
        return tools.update_inventory(tool_args.get("product_id"), tool_args.get("qty_delta"))
    elif tool_name == "create_order":
        return tools.create_order(
            customer_phone=tool_args.get("customer_phone"),
            items=tool_args.get("items", []),
            customer_name=tool_args.get("customer_name"),
            address=tool_args.get("address"),
            source=tool_args.get("source", source)
        )
    else:
        return {"error": f"Unknown tool: {tool_name}"}

def run_agent_loop(customer_phone: str, user_message: str, chat_history: List[Dict[str, Any]] = None, source: str = "web") -> str:
    """
    Main entry point for Web Chat, WhatsApp, and Voice channels.
    Takes customer phone number and message, executes agent tools iteratively,
    and returns final natural language response.
    """
    if chat_history is None:
        chat_history = []
        
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")
    
    if api_key:
        import anthropic
        try:
            client = anthropic.Anthropic(api_key=api_key)
            messages = list(chat_history)
            messages.append({"role": "user", "content": f"[Customer Phone: {customer_phone}] {user_message}"})
            
            max_turns = 5
            for _ in range(max_turns):
                response = client.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=1024,
                    system=SYSTEM_PROMPT,
                    tools=TOOL_SCHEMAS,
                    messages=messages
                )
                
                if response.stop_reason == "tool_use":
                    messages.append({"role": "assistant", "content": response.content})
                    
                    tool_results = []
                    for block in response.content:
                        if block.type == "tool_use":
                            tool_name = block.name
                            tool_args = block.input
                            tool_call_id = block.id
                            
                            if tool_name == "create_order" and "customer_phone" not in tool_args:
                                tool_args["customer_phone"] = customer_phone
                                
                            result = execute_tool(tool_name, tool_args)
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": tool_call_id,
                                "content": json.dumps(result)
                            })
                    
                    messages.append({"role": "user", "content": tool_results})
                else:
                    text_content = ""
                    for block in response.content:
                        if hasattr(block, "text"):
                            text_content += block.text
                    return text_content
                    
            return "Dhanyawad! Apka order process ho raha hai."
        except Exception as exc:
            print(f"[WARNING] Anthropic API failed ({exc}). Falling back to OpenAI or offline mode.")

    if openai_key:
        import openai
        try:
            client = openai.OpenAI(api_key=openai_key)
            
            oai_tools = [
                {
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t["description"],
                        "parameters": t["input_schema"]
                    }
                }
                for t in TOOL_SCHEMAS
            ]
            
            messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            messages.extend(chat_history)
            messages.append({"role": "user", "content": f"[Customer Phone: {customer_phone}] {user_message}"})
            
            max_turns = 5
            for _ in range(max_turns):
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=messages,
                    tools=oai_tools,
                    tool_choice="auto"
                )
                msg = response.choices[0].message
                
                if msg.tool_calls:
                    msg_dict = msg.model_dump() if hasattr(msg, "model_dump") else msg
                    messages.append(msg_dict)
                    for tc in msg.tool_calls:
                        fn_name = tc.function.name
                        fn_args = json.loads(tc.function.arguments)
                        if fn_name == "create_order" and "customer_phone" not in fn_args:
                            fn_args["customer_phone"] = customer_phone
                        res = execute_tool(fn_name, fn_args, source=source)
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": json.dumps(res)
                        })
                else:
                    return msg.content or "Order process ho gaya hai."
                    
            return "Order receive ho gaya hai, dhanyawad!"
        except Exception as exc:
            print(f"[WARNING] OpenAI API call failed ({exc}). Falling back to offline simulation.")

    return run_offline_simulation(customer_phone, user_message, source=source)

def run_offline_simulation(customer_phone: str, user_message: str, source: str = "web") -> str:
    """Intelligent fallback agent logic with live database catalog, quantity parsing, and out-of-stock substitutions."""
    import re
    msg_lower = user_message.lower()
    
    # 1. Check for specific out-of-stock scenario: Mustard Oil -> Sunflower Oil
    if "mustard" in msg_lower:
        p = tools.search_product("mustard")
        if p and p[0]["stock"] == 0:
            alt = tools.search_product("sunflower")
            alt_name = alt[0]["name"] if alt else "Fortune Sunlite Sunflower Oil 1L"
            alt_price = alt[0]["price"] if alt else 145.0
            return (
                f"Bhaiya, Fortune Mustard Oil 1L filhaal out of stock hai. "
                f"Kya main aapko {alt_name} (Rs.{alt_price:.0f}) bhej doon?"
            )

    # 2. Check for low stock 10kg Atta scenario
    if "10kg" in msg_lower and "atta" in msg_lower:
        p = tools.search_product("10kg")
        if p and p[0]["stock"] < 2:
            return f"Bhaiya, Aashirvaad Atta 10kg me sirf {p[0]['stock']} packet bacha hai. Kya aap 5kg packet le lenge?"

    # 3. Dynamic product matching across live catalog
    catalog = tools.get_all_products()
    items_to_order = []
    
    # Helper to extract quantity associated with product keyword
    def extract_qty(text, keyword):
        # Look for patterns like "2 packet atta", "3 maggi", "ek butter", "do doodh"
        hindi_nums = {"ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "panch": 5, "paanch": 5}
        for h_word, val in hindi_nums.items():
            if re.search(rf"\b{h_word}\b(?:\s+\w+)?\s+{keyword}", text):
                return val
        
        # Match digit before or after keyword, e.g. "2 packets atta" or "atta 2"
        m1 = re.search(rf"(\d+)\s*(?:packets?|pack|pkt|ltr|kg|can|bottles?|piece|pcs?)?\s+(?:of\s+)?{keyword}", text)
        if m1:
            return int(m1.group(1))
        m2 = re.search(rf"{keyword}\s*[:\-]?\s*(\d+)", text)
        if m2:
            return int(m2.group(1))
        return 1

    # Product keyword mappings to catalog items
    keyword_map = [
        ("atta 10kg", ["atta 10kg", "10kg atta"]),
        ("atta", ["atta", "aashirvaad", "aata"]),
        ("sunflower", ["sunflower", "fortune sunlite"]),
        ("oil", ["oil", "tel"]),
        ("maggi", ["maggi", "noodles", "maggie"]),
        ("butter", ["butter", "makhan", "amul butter"]),
        ("milk", ["milk", "doodh", "taaza", "amul milk"]),
        ("salt", ["salt", "namak", "tata salt"]),
        ("surf", ["surf", "surf excel", "powder", "detergent", "easy wash"]),
        ("tea", ["tea", "chai", "taj mahal"]),
        ("biscuit", ["biscuit", "biscuits", "good day", "cashew biscuit"]),
        ("soap", ["soap", "dettol", "sabun"])
    ]

    matched_product_ids = set()
    for key_tag, aliases in keyword_map:
        for alias in aliases:
            if re.search(rf"\b{re.escape(alias)}\b", msg_lower):
                # Search database for this item
                prods = tools.search_product(key_tag)
                if prods:
                    chosen = prods[0]
                    if chosen["id"] not in matched_product_ids:
                        matched_product_ids.add(chosen["id"])
                        qty = extract_qty(msg_lower, alias)
                        items_to_order.append({
                            "product_id": chosen["id"],
                            "quantity": qty,
                            "name": chosen["name"]
                        })
                break

    if not items_to_order:
        # Check if greeting
        if any(g in msg_lower for g in ["namaste", "hello", "hi", "kaise ho", "kya haal"]):
            return "Namaste bhaiya! Zero-Click Kirana mein aapka swagat hai. Aaj ghar ke liye kya deliver karwaana hai? Humare paas Atta, Fortune Oil, Maggi, Butter, Doodh, Salt sab fresh stock mein hai!"
        return "Namaste! Aapko kya mangwana hai? Humare paas Atta, Fortune Oil, Maggi, Butter, Salt sab available hai."

    # Validate stock before ordering
    for it in items_to_order:
        inv = tools.check_inventory(it["product_id"])
        if inv.get("stock", 0) <= 0:
            return f"Bhaiya, {it['name']} filhaal out of stock hai. Kya koi dusra brand bhej doon?"
        if inv.get("stock", 0) < it["quantity"]:
            return f"Bhaiya, {it['name']} me sirf {inv['stock']} available hai. Kya utna bhej doon?"

    order_items = [{"product_id": item["product_id"], "quantity": item["quantity"]} for item in items_to_order]
    order_res = tools.create_order(customer_phone=customer_phone, items=order_items, source=source)
    
    if "error" in order_res:
        return f"Sorry bhaiya, order placement me issue aaya: {order_res['error']}"
        
    summary_lines = []
    for it in order_res["items"]:
        summary_lines.append(f"- {it['name']} x {it['quantity']}: Rs.{it['item_total']:.0f}")
        
    summary_str = "\n".join(summary_lines)
    return (
        f" Haanji bhaiya! Aapka order confirm ho gaya hai:\n\n"
        f"{summary_str}\n\n"
        f" Total Amount: Rs.{order_res['total_amount']:.0f}\n"
        f" Order ID: #{order_res['order_id']}\n"
        f"Ghar pe deliver kar diya jayega. Dhanyawad!"
    )

