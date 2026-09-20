import os
from typing import List, Optional
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from ai.agent import run_agent_loop
from backend import tools
from phonecall.main import app as phonecall_app

app = FastAPI(
    title="Zero-Click Store Operator API & Portal",
    description="Autonomous Kirana Store Operator with Customer Front & Admin Portal",
    version="1.0.0"
)

# Enable CORS for local & remote browser interactions
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount phonecall app sub-router
app.mount("/phone", phonecall_app)

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")

# Mount frontend directory for static assets (CSS, JS, icons)
if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


# =====================================================================
# PAGE ROUTES
# =====================================================================
@app.get("/")
def home():
    index_file = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"status": "ok", "service": "Zero-Click Store Operator Agent API"}


@app.get("/store")
def store_page():
    index_file = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return JSONResponse({"error": "Store frontend not found"}, status_code=404)


@app.get("/admin")
def admin_page():
    admin_file = os.path.join(FRONTEND_DIR, "admin.html")
    if os.path.exists(admin_file):
        return FileResponse(admin_file)
    return JSONResponse({"error": "Admin portal not found"}, status_code=404)


@app.get("/health")
@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "Zero-Click Store Operator Agent API"}


@app.post("/agent/chat")
async def chat_endpoint(request: Request):
    """
    Direct API endpoint for testing agent responses.
    JSON Payload: {"phone": "+919876543210", "message": "2 packets Atta"}
    """
    data = await request.json()
    phone = data.get("phone", "+910000000000")
    message = data.get("message", "")
    
    if not message:
        return JSONResponse({"error": "message is required"}, status_code=400)
        
    reply = run_agent_loop(customer_phone=phone, user_message=message)
    return {"phone": phone, "message": message, "reply": reply}


# =====================================================================
# REST ENDPOINTS FOR SHARED BACKEND (Used by Phonecall & External Clients)
# =====================================================================

@app.get("/api/products/search")
def search_products(q: str = ""):
    """
    Search for products by query string.
    Returns: {"products": [...]}
    """
    products = tools.search_product(q)
    return {"products": products}


@app.get("/api/products/{product_id}")
def get_product_inventory(product_id: int):
    """
    Get inventory details for a specific product ID.
    """
    res = tools.check_inventory(product_id)
    if "error" in res:
        return JSONResponse(res, status_code=404)
    return res


class OrderItemSchema(BaseModel):
    product_id: int
    quantity: int


class CreateOrderSchema(BaseModel):
    customer_phone: str
    items: List[OrderItemSchema]
    customer_name: Optional[str] = None
    address: Optional[str] = None
    source: Optional[str] = "api"


@app.post("/api/orders")
def create_order_endpoint(payload: CreateOrderSchema):
    """
    Create a new order in the store database and deduct inventory.
    """
    items_dict = [{"product_id": item.product_id, "quantity": item.quantity} for item in payload.items]
    res = tools.create_order(
        customer_phone=payload.customer_phone,
        items=items_dict,
        customer_name=payload.customer_name,
        address=payload.address
    )
    if "error" in res:
        return JSONResponse(res, status_code=400)
    return res


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
