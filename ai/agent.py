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

def execute_tool(tool_name: str, tool_args: Dict[str, Any]) -> Any:
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
            address=tool_args.get("address")
        )
    else:
        return {"error": f"Unknown tool: {tool_name}"}

def run_agent_loop(customer_phone: str, user_message: str, chat_history: List[Dict[str, Any]] = None) -> str:
    """
    Main entry point for Member B (WhatsApp) & Member C (Voice).
    Takes customer phone number and message, executes agent tools iteratively,
    and returns final natural language response.
    """
    if chat_history is None:
        chat_history = []
        
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")
    
    if api_key:
        import anthropic
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

    elif openai_key:
        import openai
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
                messages.append(msg)
                for tc in msg.tool_calls:
                    fn_name = tc.function.name
                    fn_args = json.loads(tc.function.arguments)
                    if fn_name == "create_order" and "customer_phone" not in fn_args:
                        fn_args["customer_phone"] = customer_phone
                    res = execute_tool(fn_name, fn_args)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(res)
                    })
            else:
                return msg.content or "Order process ho gaya hai."
                
        return "Order receive ho gaya hai, dhanyawad!"

    else:
        print("[WARNING] No ANTHROPIC_API_KEY or OPENAI_API_KEY found. Running offline agent simulation.")
        return run_offline_simulation(customer_phone, user_message)

def run_offline_simulation(customer_phone: str, user_message: str) -> str:
    """Fallback agent logic with out-of-stock and substitution checks."""
    msg_lower = user_message.lower()
    
    if "mustard oil" in msg_lower or "fortune mustard" in msg_lower:
        p = tools.search_product("mustard")
        if p and p[0]["stock"] == 0:
            alt = tools.search_product("sunflower")
            alt_name = alt[0]["name"] if alt else "Fortune Sunflower Oil 1L"
            return (
                f"Bhaiya, Fortune Mustard Oil 1L filhaal out of stock hai. "
                f"Kya main aapko {alt_name} (Rs.145) bhej doon?"
            )

    items_to_order = []
    
    if "atta 10kg" in msg_lower:
        p = tools.search_product("10kg")
        if p and p[0]["stock"] < 2:
            return f"Bhaiya, Aashirvaad Atta 10kg me sirf {p[0]['stock']} packet bacha hai. Kya aap 5kg packet le lenge?"
    elif "atta" in msg_lower:
        p = tools.search_product("atta 5kg") or tools.search_product("atta")
        if p:
            items_to_order.append({"product_id": p[0]["id"], "quantity": 2, "name": p[0]["name"]})
            
    if "oil" in msg_lower and "mustard" not in msg_lower:
        p = tools.search_product("oil")
        if p:
            items_to_order.append({"product_id": p[0]["id"], "quantity": 1, "name": p[0]["name"]})
            
    if "maggi" in msg_lower:
        p = tools.search_product("maggi")
        if p:
            items_to_order.append({"product_id": p[0]["id"], "quantity": 3, "name": p[0]["name"]})
            
    if not items_to_order:
        return "Namaste! Aapko kya mangwana hai? Humare paas Atta, Fortune Oil, Maggi, Butter, Salt sab available hai."

    order_items = [{"product_id": item["product_id"], "quantity": item["quantity"]} for item in items_to_order]
    order_res = tools.create_order(customer_phone=customer_phone, items=order_items)
    
    if "error" in order_res:
        return f"Sorry bhaiya, order placement me issue aaya: {order_res['error']}"
        
    summary_lines = []
    for it in order_res["items"]:
        summary_lines.append(f"- {it['name']} x {it['quantity']}: Rs.{it['item_total']}")
        
    summary_str = "\n".join(summary_lines)
    return (
        f" Haanji bhaiya! Aapka order confirm ho gaya hai:\n\n"
        f"{summary_str}\n\n"
        f" Total Amount: Rs.{order_res['total_amount']}\n"
        f" Order ID: #{order_res['order_id']}\n"
        f"Ghar pe deliver kar diya jayega. Dhanyawad!"
    )
