from fastapi import FastAPI, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from .database import Base, engine, get_db, SessionLocal
from .models import Product, Order
from .schemas import ChatRequest
from .services import seed, summary, add_cart, clear_cart, confirm_order
from .ai import parse

Base.metadata.create_all(bind=engine)
app = FastAPI(title="Grocery WhatsApp AI Agent")

@app.on_event("startup")
def startup():
    db = SessionLocal()
    seed(db)
    db.close()

@app.get("/api/products")
def products(db: Session = Depends(get_db)):
    return [
        {"id": p.id, "name": p.name, "unit": p.unit,
         "price": p.price, "stock": p.stock}
        for p in db.query(Product).all()
    ]

@app.get("/api/cart/{customer_id}")
def cart(customer_id: str, db: Session = Depends(get_db)):
    return summary(db, customer_id)

@app.get("/api/orders")
def orders(db: Session = Depends(get_db)):
    return [
        {"order_id": f"G{o.id:05d}", "customer_id": o.customer_id,
         "status": o.status, "total": o.total}
        for o in db.query(Order).order_by(Order.id.desc()).all()
    ]

@app.post("/api/chat")
def chat(data: ChatRequest, db: Session = Depends(get_db)):
    x = parse(data.message)
    intent = x["intent"]

    try:
        if intent == "add":
            p = next((p for p in db.query(Product).all()
                      if p.name.lower() == x["product"]), None)
            if not p:
                return {"reply": "Product not found."}
            add_cart(db, data.customer_id, p.id, x["quantity"])
            return {
                "reply": f"Added {x['quantity']:g} {p.unit} {p.name} "
                          "to your temporary cart. Inventory was NOT changed.",
                "cart": summary(db, data.customer_id)
            }

        if intent == "cart":
            return {"reply": "Here is your temporary cart.",
                    "cart": summary(db, data.customer_id)}

        if intent == "checkout":
            s = summary(db, data.customer_id)
            if not s["items"]:
                return {"reply": "Your cart is empty."}
            return {
                "reply": "Please confirm your order: CONFIRM ORDER, CANCEL, or EDIT CART.",
                "cart": s, "confirmation_required": True
            }

        if intent == "cancel":
            clear_cart(db, data.customer_id)
            return {"reply": "Order cancelled. No inventory was changed."}

        if intent == "confirm":
            # Explicit confirmation reaches the ONLY permanent-write operation.
            order = confirm_order(db, data.customer_id)
            return {
                "reply": f"Order G{order.id:05d} confirmed. Total ₹{order.total:.2f}.",
                "order_id": f"G{order.id:05d}",
                "status": order.status
            }

        return {"reply": "Try: '2 kg rice', 'show cart', or 'checkout'."}

    except ValueError as e:
        return {"reply": str(e)}

# WhatsApp can later call the same /api/chat endpoint.
@app.post("/webhook/whatsapp")
def whatsapp_webhook(data: ChatRequest, db: Session = Depends(get_db)):
    return chat(data, db)

app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
