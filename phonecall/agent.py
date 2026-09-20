"""
Autonomous Phone Call Agent for Zero-Click Store Operator.

Interprets natural spoken Hindi/English/Hinglish from customer voice calls,
interacts with the team's shared backend using OpenAI tool calling,
and speaks back concise, natural Kirana shopkeeper confirmations.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional
import openai

try:
    from . import config
    from . import tools
    from .phone_session import PhoneSession
except ImportError:
    import config
    import tools
    from phone_session import PhoneSession

logger = logging.getLogger(__name__)

# =====================================================================
# SYSTEM PROMPT FOR VOICE KIRANA OPERATOR
# =====================================================================
SYSTEM_PROMPT = f"""You are the friendly AI Kirana Store Operator at "{config.STORE_NAME}", taking customer orders over a live phone call.

COMMUNICATION STYLE (CRITICAL FOR VOICE CALLS):
1. Language: Speak natural conversational Hinglish/Hindi (mirror the customer's language mix).
   - If customer speaks Hindi/Hinglish, reply in warm, casual Hindi/Hinglish ("Haanji bhaiya", "Ho gaya bhaiya").
   - If customer speaks English, reply in friendly English.
2. Brevity: Keep responses SHORT, natural, and conversational (1 to 2 sentences max). The customer is on a phone call.
3. Voice-Friendly Formatting:
   - NEVER use markdown formatting (no asterisks **, no bullet points -, no headers #).
   - NEVER use emojis.
   - Say amounts naturally (e.g. "260 rupaye" or "Rs 260").
   - Bad: "Your order #123 has been processed. Items: * 2 Atta - Rs 110".
   - Good: "Ho gaya bhaiya. Do packet atta aur ek oil add kar diya hai. Total 260 rupaye hue."

AUTONOMOUS AGENT RULES:
1. Product Search:
   - Always call `search_product` first when the customer asks for an item (e.g. "atta", "oil", "maggi").
   - The backend is the ONLY source of truth. NEVER invent product names, stock, or prices.
2. Ambiguous Products:
   - If a customer asks for a generic category with multiple matches (e.g. "oil", "atta"), ask a short clarification question:
     "Bhaiya oil kaunsa chahiye, Fortune sunflower ya mustard?"
3. Out-Of-Stock / Insufficient Stock:
   - If requested quantity is not available: NEVER silently substitute or drop it.
   - Tell the customer clearly what is unavailable and suggest an available alternative returned by the backend:
     "Bhaiya mustard oil khatam hai, kya Sunflower oil bhej doon?"
   - ONLY create the order after the customer explicitly agrees to the substitution.
4. Order Creation:
   - When the customer's order is clear, in stock, and confirmed, call `create_order` with their phone number and item list.
   - Once `create_order` returns success with order_id and total, speak a warm, short confirmation with the total amount.
"""


def clean_for_voice(text: str) -> str:
    """
    Cleans up LLM output for Text-to-Speech (TTS).
    Removes markdown formatting (*, _, #, bullets, backticks), URLs, and emojis.
    """
    if not text:
        return ""
    
    # Remove markdown headers, bold, italics, code blocks
    cleaned = re.sub(r"[\*\_#`~]", "", text)
    # Remove bullet points at line starts
    cleaned = re.sub(r"^\s*[-•]\s*", "", cleaned, flags=re.MULTILINE)
    # Remove emoji characters
    cleaned = re.sub(
        r"[\U00010000-\U0010ffff\u2600-\u26ff\u2700-\u27bf]",
        "",
        cleaned
    )
    # Replace multiple spaces / newlines with a single clean space
    cleaned = " ".join(cleaned.split())
    return cleaned.strip()


async def run_voice_agent(
    session: PhoneSession,
    customer_speech: str
) -> str:
    """
    Autonomous agent execution loop for a customer speech turn:
    1. Records customer speech in session history.
    2. Runs OpenAI tool-calling loop (calling search_product, check_inventory, create_order).
    3. Returns natural, voice-ready response text.
    """
    session.add_user_message(customer_speech)

    # Check if OpenAI API key is configured
    if not config.OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY is not configured. Running fallback simulation.")
        fallback_reply = await run_offline_fallback(session.customer_phone, customer_speech)
        session.add_assistant_message(fallback_reply)
        return fallback_reply

    client = openai.AsyncOpenAI(api_key=config.OPENAI_API_KEY)

    # Construct conversation payload: system prompt + existing message history
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]
    # Include session conversation history (truncated to last 12 turns for context & latency)
    messages.extend(session.messages[-12:])

    max_turns = 5
    for turn_idx in range(max_turns):
        try:
            logger.info("Calling OpenAI (%s) turn %d for CallSid %s", config.OPENAI_MODEL, turn_idx + 1, session.call_sid)
            response = await client.chat.completions.create(
                model=config.OPENAI_MODEL,
                messages=messages,
                tools=tools.TOOL_DEFINITIONS,
                tool_choice="auto",
                temperature=0.3,
                max_tokens=300,
            )
        except Exception as exc:
            logger.exception("OpenAI API call failed: %s", exc)
            return "Maaf kijiye bhaiya, system me thodi dikkat aa rahi hai. Kya aap dobara bol sakte hain?"

        assistant_msg = response.choices[0].message

        # Check if the agent wants to call tools
        if assistant_msg.tool_calls:
            # Append assistant message with tool calls
            messages.append(assistant_msg)
            session.add_raw_message(assistant_msg.model_dump())

            for tool_call in assistant_msg.tool_calls:
                fn_name = tool_call.function.name
                call_id = tool_call.id
                raw_args = tool_call.function.arguments or "{}"

                try:
                    fn_args = json.loads(raw_args)
                except Exception:
                    fn_args = {}

                # Automatically pass session customer_phone if missing in create_order
                if fn_name == "create_order" and not fn_args.get("customer_phone"):
                    fn_args["customer_phone"] = session.customer_phone

                logger.info("Executing tool [%s] args: %s", fn_name, fn_args)
                tool_result = await tools.execute_tool(
                    tool_name=fn_name,
                    arguments=fn_args,
                    default_phone=session.customer_phone
                )

                tool_response_str = json.dumps(tool_result, ensure_ascii=False)
                tool_payload = {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": tool_response_str
                }
                messages.append(tool_payload)
                session.add_raw_message(tool_payload)

        else:
            # Final text response generated by agent
            raw_text = assistant_msg.content or "Theek hai bhaiya."
            spoken_reply = clean_for_voice(raw_text)
            session.add_assistant_message(spoken_reply)
            logger.info("Final agent response for CallSid %s: '%s'", session.call_sid, spoken_reply)
            return spoken_reply

    # If max turns reached
    fallback = "Theek hai bhaiya, aapka order note ho raha hai. Dhanyawad!"
    session.add_assistant_message(fallback)
    return fallback


async def run_offline_fallback(customer_phone: str, customer_speech: str) -> str:
    """
    Offline fallback simulation when OPENAI_API_KEY is not set.
    Allows testing voice channel even without active API keys.
    """
    text_lower = customer_speech.lower()

    if any(greet in text_lower for greet in ["namaste", "hello", "hi", "kaise ho"]):
        return "Namaste bhaiya! Boliye, aaj kya mangwana hai? Atta, oil, maggi sab available hai."

    if "mustard" in text_lower:
        search_res = await tools.search_product("sunflower")
        alt = search_res.get("products", [])
        alt_name = alt[0]["name"] if alt else "Fortune Sunflower Oil"
        return f"Bhaiya Fortune Mustard Oil out of stock hai. Kya {alt_name} bhej doon?"

    if "oil" in text_lower or "tel" in text_lower:
        # Check backend search
        search_res = await tools.search_product("oil")
        products = search_res.get("products", [])
        if products:
            names = [p["name"] for p in products[:2]]
            return f"Bhaiya hamare paas {', '.join(names)} hai. Kaunsa bhej doon?"
        return "Bhaiya oil me Fortune Sunflower aur Mustard dono hai. Kaunsa chahiye?"

    if "maggi" in text_lower or "atta" in text_lower or "butter" in text_lower or "milk" in text_lower or "salt" in text_lower:
        kw = "maggi" if "maggi" in text_lower else ("atta" if "atta" in text_lower else ("butter" if "butter" in text_lower else "milk"))
        search_res = await tools.search_product(kw)
        products = search_res.get("products", [])
        if products:
            p = products[0]
            if p["stock"] > 0:
                # Try creating order
                order_res = await tools.create_order(
                    customer_phone=customer_phone,
                    items=[{"product_id": p["id"], "quantity": 1}]
                )
                if "order_id" in order_res:
                    tot = order_res.get("total", order_res.get("total_amount", p["price"]))
                    return f"Ho gaya bhaiya. {p['name']} add kar diya hai. Total {tot} rupaye hue."
            else:
                return f"Bhaiya {p['name']} out of stock hai. Kya koi dusra option bhej doon?"

    return f"Ji bhaiya, aapne kaha: {customer_speech}. Kya iska order confirm kar doon?"
