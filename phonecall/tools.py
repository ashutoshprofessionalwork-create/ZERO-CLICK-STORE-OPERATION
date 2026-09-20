"""
Backend Tools Integration for Phone Call Voice Channel.

This module connects the AI Agent to the team's shared backend REST API using httpx.
Per hackathon architecture, the shared backend is the single source of truth
for inventory, pricing, and order creation.

BACKEND REST CONTRACT:
1. GET  {BACKEND_URL}/api/products/search?q={query}
2. GET  {BACKEND_URL}/api/products/{product_id}
3. POST {BACKEND_URL}/api/orders
"""

import logging
from typing import Any, Dict, List, Optional
import httpx

try:
    from . import config
except ImportError:
    import config

logger = logging.getLogger(__name__)

# =====================================================================
# OPENAI TOOL SCHEMAS FOR FUNCTION CALLING
# =====================================================================
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_product",
            "description": (
                "Search the store's inventory for products by name or keyword "
                "(e.g. 'atta', 'oil', 'maggi', 'butter'). Always call this first "
                "to find exact product names, IDs, stock levels, and prices."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Product search keyword or brand (e.g., 'atta', 'maggi', 'fortune oil')"
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_inventory",
            "description": (
                "Check current available stock and price for a specific product ID. "
                "Use this to verify stock availability before confirming an order."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {
                        "type": "integer",
                        "description": "The unique product ID"
                    }
                },
                "required": ["product_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_order",
            "description": (
                "Submit a confirmed order to the shared backend. "
                "The backend handles inventory deduction and order creation atomically. "
                "ONLY call this when the customer has clearly confirmed the items and quantities."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_phone": {
                        "type": "string",
                        "description": "Customer phone number in international or local format (e.g. '+919876543210')"
                    },
                    "items": {
                        "type": "array",
                        "description": "List of confirmed order items with product_id and quantity",
                        "items": {
                            "type": "object",
                            "properties": {
                                "product_id": {
                                    "type": "integer",
                                    "description": "Product ID"
                                },
                                "quantity": {
                                    "type": "integer",
                                    "description": "Quantity to order (must be positive integer)"
                                }
                            },
                            "required": ["product_id", "quantity"]
                        }
                    }
                },
                "required": ["customer_phone", "items"],
            },
        },
    }
]


# =====================================================================
# ASYNC BACKEND REST API CLIENT CALLS
# =====================================================================

async def search_product(query: str) -> Dict[str, Any]:
    """
    Calls: GET {BACKEND_URL}/api/products/search?q={query}
    
    Expected response from shared backend:
    {
      "products": [
        {
          "id": 123,
          "name": "Aashirvaad Atta 1kg",
          "price": 55,
          "stock": 20
        }
      ]
    }
    """
    clean_query = query.strip()
    target_url = f"{config.BACKEND_URL}/api/products/search"
    params = {"q": clean_query}

    logger.info("Calling backend API -> %s?q=%s", target_url, clean_query)

    try:
        async with httpx.AsyncClient(timeout=config.BACKEND_TIMEOUT) as client:
            response = await client.get(target_url, params=params)
            
            if response.status_code == 200:
                data = response.json()
                products = data.get("products", [])
                if not products:
                    return {
                        "products": [],
                        "message": f"Dukaan par '{clean_query}' nahi mila."
                    }
                return data
            
            elif response.status_code == 404:
                return {
                    "products": [],
                    "message": f"'{clean_query}' store inventory me available nahi hai."
                }
            else:
                logger.error("Backend error %s: %s", response.status_code, response.text)
                return {
                    "error": f"Backend returned HTTP {response.status_code}",
                    "details": response.text
                }

    except httpx.ConnectError:
        try:
            from backend import tools as local_tools
            res = local_tools.search_product(clean_query)
            return {"products": res}
        except Exception:
            pass
        err_msg = (
            f"Cannot connect to team's backend at {config.BACKEND_URL}. "
            "Please ensure teammate's backend server is running."
        )
        logger.error(err_msg)
        return {"error": "backend_offline", "message": err_msg}
    except httpx.TimeoutException:
        logger.error("Backend request timed out after %s seconds", config.BACKEND_TIMEOUT)
        return {"error": "backend_timeout", "message": "Backend took too long to respond."}
    except Exception as exc:
        logger.exception("Unexpected error calling search_product: %s", exc)
        return {"error": "unexpected_error", "message": str(exc)}


async def check_inventory(product_id: int) -> Dict[str, Any]:
    """
    Calls: GET {BACKEND_URL}/api/products/{product_id}
    
    Expected response from shared backend:
    {
      "id": 123,
      "name": "Aashirvaad Atta 1kg",
      "price": 55,
      "stock": 20
    }
    """
    target_url = f"{config.BACKEND_URL}/api/products/{product_id}"
    logger.info("Calling backend API -> %s", target_url)

    try:
        async with httpx.AsyncClient(timeout=config.BACKEND_TIMEOUT) as client:
            response = await client.get(target_url)

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                return {"error": "not_found", "message": f"Product ID {product_id} nahi mila."}
            else:
                logger.error("Backend error %s: %s", response.status_code, response.text)
                return {"error": f"HTTP {response.status_code}", "details": response.text}

    except httpx.ConnectError:
        try:
            from backend import tools as local_tools
            res = local_tools.check_inventory(product_id)
            if "error" not in res:
                return res
            return {"error": "not_found", "message": f"Product ID {product_id} nahi mila."}
        except Exception:
            pass
        err_msg = f"Cannot connect to team backend at {config.BACKEND_URL}."
        logger.error(err_msg)
        return {"error": "backend_offline", "message": err_msg}
    except httpx.TimeoutException:
        logger.error("Backend request timed out for product_id %s", product_id)
        return {"error": "backend_timeout", "message": "Backend took too long to respond."}
    except Exception as exc:
        logger.exception("Unexpected error in check_inventory: %s", exc)
        return {"error": "unexpected_error", "message": str(exc)}


async def create_order(customer_phone: str, items: List[Dict[str, int]]) -> Dict[str, Any]:
    """
    Calls: POST {BACKEND_URL}/api/orders
    
    Payload:
    {
      "customer_phone": "+919876543210",
      "source": "phone",
      "items": [
        {
          "product_id": 123,
          "quantity": 2
        }
      ]
    }
    
    Expected response from shared backend:
    {
      "order_id": "ORD-1042",
      "status": "confirmed",
      "total": 110,
      "items": [...]
    }
    """
    target_url = f"{config.BACKEND_URL}/api/orders"
    payload = {
        "customer_phone": customer_phone,
        "source": "phone",
        "items": items
    }
    logger.info("Submitting order to backend -> %s with payload: %s", target_url, payload)

    try:
        async with httpx.AsyncClient(timeout=config.BACKEND_TIMEOUT) as client:
            response = await client.post(target_url, json=payload)

            if response.status_code in (200, 201):
                data = response.json()
                logger.info("Order successfully created on backend: Order ID %s", data.get("order_id"))
                return data
            else:
                logger.error("Order creation failed on backend: HTTP %s: %s", response.status_code, response.text)
                try:
                    err_json = response.json()
                    return {"error": f"HTTP {response.status_code}", "details": err_json}
                except Exception:
                    return {"error": f"HTTP {response.status_code}", "details": response.text}

    except httpx.ConnectError:
        try:
            from backend import tools as local_tools
            res = local_tools.create_order(
                customer_phone=customer_phone,
                items=items,
                source="phone"
            )
            if "error" not in res:
                return res
            return {"error": "order_failed", "details": res.get("error")}
        except Exception:
            pass
        err_msg = f"Cannot connect to team backend at {config.BACKEND_URL} to create order."
        logger.error(err_msg)
        return {"error": "backend_offline", "message": err_msg}
    except httpx.TimeoutException:
        logger.error("Backend request timed out creating order for phone %s", customer_phone)
        return {"error": "backend_timeout", "message": "Backend took too long to create order."}
    except Exception as exc:
        logger.exception("Unexpected error in create_order: %s", exc)
        return {"error": "unexpected_error", "message": str(exc)}


async def execute_tool(tool_name: str, arguments: Dict[str, Any], default_phone: Optional[str] = None) -> Dict[str, Any]:
    """
    Dispatches OpenAI function call to the corresponding backend REST tool.
    """
    logger.info("Executing tool [%s] with arguments: %s", tool_name, arguments)

    if tool_name == "search_product":
        query = arguments.get("query", "")
        return await search_product(query=query)

    elif tool_name == "check_inventory":
        product_id = arguments.get("product_id")
        if product_id is None:
            return {"error": "missing_parameter", "message": "product_id is required"}
        return await check_inventory(product_id=int(product_id))

    elif tool_name == "create_order":
        phone = arguments.get("customer_phone") or default_phone or ""
        items = arguments.get("items", [])
        if not items:
            return {"error": "missing_parameter", "message": "items list is required"}
        return await create_order(customer_phone=phone, items=items)

    else:
        logger.warning("Unrecognized tool name requested by agent: %s", tool_name)
        return {"error": "unknown_tool", "message": f"Tool '{tool_name}' not implemented"}
