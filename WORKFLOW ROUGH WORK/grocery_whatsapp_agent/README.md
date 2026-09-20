# Grocery WhatsApp AI Agent

Local prototype using Python, FastAPI and SQLite.

CRITICAL RULE: adding to the cart never reduces inventory. Permanent data changes happen only after explicit confirmation.

Run:
```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000

Try:
1. `2 kg rice`
2. `1 litre milk`
3. `checkout`
4. `confirm order`

Inventory changes only at step 4.
