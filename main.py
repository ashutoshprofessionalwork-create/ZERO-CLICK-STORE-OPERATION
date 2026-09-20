import os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from ai.agent import run_agent_loop
from backend import tools

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


# =====================================================================
# REST APIs FOR PRODUCTS & INVENTORY
# =====================================================================
@app.get("/api/products")
def list_products():
    return tools.get_all_products()


@app.post("/api/products")
async def create_product(request: Request):
    data = await request.json()
    name = data.get("name")
    price = float(data.get("price", 0))
    stock = int(data.get("stock", 0))
    threshold = int(data.get("low_stock_threshold", 5))

    if not name or price <= 0:
        return JSONResponse({"error": "Valid name and positive price required"}, status_code=400)

    new_prod = tools.add_product(name, price, stock, threshold)
    return new_prod


@app.post("/api/inventory/update")
async def update_stock(request: Request):
    data = await request.json()
    product_id = data.get("product_id")
    qty_delta = data.get("qty_delta")

    if product_id is None or qty_delta is None:
        return JSONResponse({"error": "product_id and qty_delta are required"}, status_code=400)

    res = tools.update_inventory(int(product_id), int(qty_delta))
    if "error" in res:
        return JSONResponse(res, status_code=400)
    return res


# =====================================================================
# REST APIs FOR ORDERS
# =====================================================================
@app.get("/api/orders")
def list_orders():
    return tools.get_all_orders()


@app.post("/api/orders")
async def place_order(request: Request):
    data = await request.json()
    phone = data.get("customer_phone", "+910000000000")
    items = data.get("items", [])
    name = data.get("customer_name")
    address = data.get("address")

    if not items:
        return JSONResponse({"error": "Items list cannot be empty"}, status_code=400)

    res = tools.create_order(phone, items, name, address)
    if "error" in res:
        return JSONResponse(res, status_code=400)
    return res


@app.post("/api/orders/{order_id}/status")
async def change_order_status(order_id: int, request: Request):
    data = await request.json()
    status = data.get("status", "confirmed")
    return tools.update_order_status(order_id, status)


# =====================================================================
# REST APIs FOR STORE STATS & DASHBOARD
# =====================================================================
@app.get("/api/stats")
def store_stats():
    return tools.get_store_stats()


# =====================================================================
# AI AGENT CHAT ENDPOINT
# =====================================================================
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


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
