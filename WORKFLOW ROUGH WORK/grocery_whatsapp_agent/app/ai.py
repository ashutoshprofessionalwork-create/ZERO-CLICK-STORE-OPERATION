import re

# Local prototype parser. It NEVER changes the database.
# Later this can be replaced by an LLM that returns structured intent.

ALIASES = {
    "rice": ["rice", "chawal"],
    "milk": ["milk", "doodh"],
    "maggi": ["maggi", "noodles"],
}

def number(text):
    m = re.search(r"\b(\d+(?:\.\d+)?)\b", text)
    return float(m.group(1)) if m else 1.0

def product(text):
    text = text.lower()
    for name, aliases in ALIASES.items():
        if any(a in text for a in aliases):
            return name
    return None

def parse(message):
    t = message.lower().strip()

    if t in {"yes", "confirm", "confirm order", "place order", "place the order"}:
        return {"intent": "confirm"}
    if "checkout" in t or "order summary" in t:
        return {"intent": "checkout"}
    if "cancel" in t:
        return {"intent": "cancel"}
    if "cart" in t:
        return {"intent": "cart"}

    p = product(t)
    if p:
        return {"intent": "add", "product": p, "quantity": number(t)}

    return {"intent": "unknown"}
