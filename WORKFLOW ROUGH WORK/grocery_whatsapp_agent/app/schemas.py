from pydantic import BaseModel

class AddCartRequest(BaseModel):
    customer_id: str
    product_id: int
    quantity: float

class ConfirmRequest(BaseModel):
    customer_id: str

class ChatRequest(BaseModel):
    customer_id: str
    message: str
