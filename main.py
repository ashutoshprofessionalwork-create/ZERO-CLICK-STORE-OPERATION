from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn
from ai.agent import run_agent_loop

app = FastAPI(title="Zero-Click Store Operator API")

@app.get("/")
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

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
