"""
Configuration module for the Phone Call Voice Channel.

Handles environment variables, backend URL setup, and Twilio voice settings.
"""

import os
from dotenv import load_dotenv

# Load variables from .env file if present
load_dotenv()

# =====================================================================
# TEAM BACKEND CONFIGURATION
# =====================================================================
# This URL points to the shared backend REST API built by teammates.
# Default is http://localhost:8000 for local development.
# If teammates deploy to a cloud or ngrok URL, update BACKEND_URL in .env:
# e.g., BACKEND_URL=https://abc123.ngrok-free.app or http://192.168.1.50:8000
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/")

# Timeout in seconds for backend HTTP requests
BACKEND_TIMEOUT = float(os.getenv("BACKEND_TIMEOUT", "6.0"))

# =====================================================================
# OPENAI & LLM CONFIGURATION
# =====================================================================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# Toggle between:
# - False: Basic Twilio Voice loop without LLM (incoming call -> greeting -> Gather speech -> print transcript -> Say transcript)
# - True: Full autonomous OpenAI agent with backend tool calling (search_product, check_inventory, create_order)
# Defaults to True ONLY if OPENAI_API_KEY is provided, or can be forced via ENABLE_LLM_AGENT=true/false
_enable_agent_env = os.getenv("ENABLE_LLM_AGENT")
if _enable_agent_env is not None:
    ENABLE_LLM_AGENT = _enable_agent_env.lower() in ("true", "1", "yes")
else:
    ENABLE_LLM_AGENT = bool(OPENAI_API_KEY.strip())

# =====================================================================
# TWILIO VOICE SETTINGS
# =====================================================================
# Language for Twilio <Gather input="speech"> and <Say>
# "hi-IN" provides optimal recognition for conversational Hindi and Hinglish
TWILIO_VOICE_LANGUAGE = os.getenv("TWILIO_VOICE_LANGUAGE", "hi-IN")

# Amazon Polly Hindi voice supported natively by Twilio Voice:
# "Polly.Aditi" provides natural, conversational Indian voice delivery
TWILIO_VOICE_NAME = os.getenv("TWILIO_VOICE_NAME", "Polly.Aditi")

# Initial greeting spoken to customer upon call connection
DEFAULT_GREETING = os.getenv(
    "DEFAULT_GREETING",
    "Namaste! Zero-Click Store mein aapka swagat hai. Boliye bhaiya, aaj kya mangwana hai?"
)

# Fallback response if speech is not recognized or customer stays silent
SILENCE_PROMPT = os.getenv(
    "SILENCE_PROMPT",
    "Bhaiya aapki aawaz nahi aayi. Kya aap dobara bol sakte hain?"
)

# Store name used in system prompt and communications
STORE_NAME = os.getenv("STORE_NAME", "Zero-Click Store")

# Server host & port (default to 8001 for standalone voice server to avoid conflict with main backend on 8000)
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8001"))
