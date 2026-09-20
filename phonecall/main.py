"""
Main FastAPI Server for Phone Call Voice Channel.
Handles Twilio Voice webhooks, Speech recognition, and AI Agent execution.

ENDPOINTS:
- GET  /                : Service health check & config summary
- POST /voice           : Twilio Webhook for incoming voice calls
- POST /process-speech  : Twilio Webhook for transcribed speech from <Gather>
- POST /call-status     : Twilio Webhook for call termination / session cleanup
- POST /test-call       : Developer endpoint to simulate phone turns via JSON
"""

import logging
from typing import Optional
from fastapi import FastAPI, Request, Form, Response, Query
from fastapi.responses import JSONResponse, PlainTextResponse
from twilio.twiml.voice_response import VoiceResponse

try:
    from . import config
    from . import agent
    from .phone_session import session_manager
except ImportError:
    import config
    import agent
    from phone_session import session_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("phonecall.main")

app = FastAPI(
    title="Zero-Click Store Operator - Phone Call Channel",
    description="Twilio Voice + OpenAI tool-calling phone operator in Hindi/Hinglish",
    version="1.0.0"
)


# =====================================================================
# 1. HEALTH CHECK & STATUS
# =====================================================================
@app.get("/")
async def root():
    """Health check showing service configuration and active sessions."""
    return {
        "status": "online",
        "service": "Phone Call Voice Channel",
        "store": config.STORE_NAME,
        "backend_url": config.BACKEND_URL,
        "llm_agent_enabled": config.ENABLE_LLM_AGENT,
        "llm_model": config.OPENAI_MODEL if config.ENABLE_LLM_AGENT else "N/A (Basic Echo Mode)",
        "voice_language": config.TWILIO_VOICE_LANGUAGE,
        "voice_name": config.TWILIO_VOICE_NAME,
        "active_phone_sessions": session_manager.active_count(),
        "twilio_webhooks": {
            "incoming_call_url": "/voice",
            "speech_result_url": "/process-speech",
            "call_status_url": "/call-status"
        }
    }


# =====================================================================
# 2. INCOMING VOICE CALL HANDLER (POST /voice)
# =====================================================================
@app.api_route("/voice", methods=["GET", "POST"])
async def handle_incoming_call(
    request: Request,
    CallSid: Optional[str] = Form(None),
    From: Optional[str] = Form(None)
):
    """
    Twilio Incoming Call Webhook.
    
    1. Twilio sends POST when customer dials store phone number.
    2. Initializes session for CallSid.
    3. Greets customer in natural Hindi/Hinglish.
    4. Gathers speech input using <Gather input="speech" language="hi-IN">.
    """
    # Fallback to query params if sent via GET
    if not CallSid:
        CallSid = request.query_params.get("CallSid", "SIMULATED_CALL")
    if not From:
        From = request.query_params.get("From", "+910000000000")

    logger.info(">>> Incoming Call Received | CallSid: %s | Caller: %s", CallSid, From)

    # Initialize or refresh session state
    session = session_manager.get_or_create(call_sid=CallSid, customer_phone=From)

    # Construct TwiML response
    twiml = VoiceResponse()

    # Twilio <Gather> collects spoken audio from customer
    # language="hi-IN" provides optimal Hindi & Hinglish transcription
    gather = twiml.gather(
        input="speech",
        action="/process-speech",
        method="POST",
        language=config.TWILIO_VOICE_LANGUAGE,
        speech_timeout="auto",
        timeout=4
    )

    # Initial greeting spoken to customer
    gather.say(
        config.DEFAULT_GREETING,
        language=config.TWILIO_VOICE_LANGUAGE,
        voice=config.TWILIO_VOICE_NAME
    )

    # If customer does not speak before gather timeout:
    twiml.say(
        config.SILENCE_PROMPT,
        language=config.TWILIO_VOICE_LANGUAGE,
        voice=config.TWILIO_VOICE_NAME
    )

    # Second gather attempt
    gather_retry = twiml.gather(
        input="speech",
        action="/process-speech",
        method="POST",
        language=config.TWILIO_VOICE_LANGUAGE,
        speech_timeout="auto",
        timeout=5
    )

    # Final polite timeout goodbye if no response
    twiml.say(
        "Aapki aawaz nahi aayi. Dhanyawad!",
        language=config.TWILIO_VOICE_LANGUAGE,
        voice=config.TWILIO_VOICE_NAME
    )
    twiml.hangup()

    logger.info("Sending initial TwiML greeting to CallSid %s", CallSid)
    return Response(content=str(twiml), media_type="application/xml")


# =====================================================================
# 3. SPEECH PROCESSING HANDLER (POST /process-speech)
# =====================================================================
@app.api_route("/process-speech", methods=["GET", "POST"])
async def process_speech(
    request: Request,
    CallSid: Optional[str] = Form(None),
    From: Optional[str] = Form(None),
    SpeechResult: Optional[str] = Form(None),
    Confidence: Optional[str] = Form(None)
):
    """
    Twilio Gather Webhook.
    
    Receives transcribed speech from Twilio STT.
    - If ENABLE_LLM_AGENT is False:
        Executes basic flow: Prints transcript to console and speaks it back.
    - If ENABLE_LLM_AGENT is True:
        Sends transcript + history to OpenAI agent with backend tool calling.
    """
    # Fallback to query params if GET request
    if not CallSid:
        CallSid = request.query_params.get("CallSid", "SIMULATED_CALL")
    if not From:
        From = request.query_params.get("From", "+910000000000")
    if SpeechResult is None:
        SpeechResult = request.query_params.get("SpeechResult")

    logger.info(">>> Transcribed Speech Turn | CallSid: %s | SpeechResult: '%s' (Confidence: %s)",
                CallSid, SpeechResult, Confidence)

    session = session_manager.get_or_create(call_sid=CallSid, customer_phone=From)
    twiml = VoiceResponse()

    # Case 1: Customer remained silent or speech could not be transcribed
    if not SpeechResult or not SpeechResult.strip():
        logger.warning("No speech transcribed for CallSid %s", CallSid)
        gather = twiml.gather(
            input="speech",
            action="/process-speech",
            method="POST",
            language=config.TWILIO_VOICE_LANGUAGE,
            speech_timeout="auto",
            timeout=4
        )
        gather.say(
            config.SILENCE_PROMPT,
            language=config.TWILIO_VOICE_LANGUAGE,
            voice=config.TWILIO_VOICE_NAME
        )
        twiml.say("Aapki aawaz nahi aayi. Dhanyawad!", language=config.TWILIO_VOICE_LANGUAGE, voice=config.TWILIO_VOICE_NAME)
        twiml.hangup()
        return Response(content=str(twiml), media_type="application/xml")

    # =================================================================
    # FLOW BRANCHING:
    # 1. BASIC VOICE FLOW (WITHOUT LLM):
    #    incoming call -> greeting -> Gather speech -> print transcript -> Say transcript
    # 2. OPENAI AGENT FLOW (WITH LLM):
    #    transcription -> OpenAI agent with tools -> backend REST -> spoken confirmation
    # =================================================================
    if not config.ENABLE_LLM_AGENT:
        # STEP 1: Basic Twilio voice flow WITHOUT LLM
        print("\n" + "=" * 50)
        print("[BASIC TWILIO VOICE FLOW - NO LLM]")
        print(f"CallSid:    {CallSid}")
        print(f"Caller:     {From}")
        print(f"Transcript: '{SpeechResult}'")
        print("=" * 50 + "\n")

        spoken_response = f"Aapne kaha: {SpeechResult}"
        session.add_user_message(SpeechResult)
        session.add_assistant_message(spoken_response)

    else:
        # STEP 2: Full OpenAI agent integration with backend tools
        spoken_response = await agent.run_voice_agent(
            session=session,
            customer_speech=SpeechResult
        )

    # Check if caller wants to end the call
    lower_input = SpeechResult.lower()
    is_farewell = any(w in lower_input for w in ["bye", "alvida", "chalta hoon", "rakhta hoon", "bas itna hi"])

    # Build TwiML response
    if is_farewell:
        twiml.say(
            spoken_response,
            language=config.TWILIO_VOICE_LANGUAGE,
            voice=config.TWILIO_VOICE_NAME
        )
        twiml.say(
            "Dhanyawad bhaiya, call karne ke liye!",
            language=config.TWILIO_VOICE_LANGUAGE,
            voice=config.TWILIO_VOICE_NAME
        )
        twiml.hangup()
    else:
        # Continue the conversation with another <Gather>
        gather = twiml.gather(
            input="speech",
            action="/process-speech",
            method="POST",
            language=config.TWILIO_VOICE_LANGUAGE,
            speech_timeout="auto",
            timeout=4
        )
        gather.say(
            spoken_response,
            language=config.TWILIO_VOICE_LANGUAGE,
            voice=config.TWILIO_VOICE_NAME
        )

        # Fallback if no further speech
        twiml.say(
            "Theek hai bhaiya, agar kuch aur chahiye toh dobara call karein. Dhanyawad!",
            language=config.TWILIO_VOICE_LANGUAGE,
            voice=config.TWILIO_VOICE_NAME
        )
        twiml.hangup()

    logger.info("Returning TwiML to CallSid %s with spoken text: '%s'", CallSid, spoken_response)
    return Response(content=str(twiml), media_type="application/xml")


# =====================================================================
# 4. CALL STATUS / TERMINATION WEBHOOK (POST /call-status)
# =====================================================================
@app.api_route("/call-status", methods=["GET", "POST"])
async def call_status_webhook(
    request: Request,
    CallSid: Optional[str] = Form(None),
    CallStatus: Optional[str] = Form(None)
):
    """
    Twilio StatusCallback webhook.
    Cleans up session history when call is completed or cancelled.
    """
    if not CallSid:
        CallSid = request.query_params.get("CallSid")
    if not CallStatus:
        CallStatus = request.query_params.get("CallStatus", "unknown")

    logger.info("Call Status Update | CallSid: %s | Status: %s", CallSid, CallStatus)

    if CallStatus in ("completed", "failed", "busy", "no-answer", "canceled"):
        session_manager.remove(CallSid)

    return {"status": "received", "call_sid": CallSid, "call_status": CallStatus}


# =====================================================================
# 5. DEVELOPER SIMULATION ENDPOINT (POST /test-call)
# =====================================================================
@app.post("/test-call")
async def test_call_endpoint(payload: dict):
    """
    Developer testing endpoint to simulate phone turns via JSON.
    Useful for testing Hinglish speech understanding and backend orders
    without placing a physical phone call.
    
    JSON Request Body:
    {
      "call_sid": "DEV-TEST-001",
      "phone": "+919876543210",
      "speech": "bhaiya do packet maggi aur ek Parle-G dena"
    }
    """
    call_sid = payload.get("call_sid", "DEV-TEST-001")
    phone = payload.get("phone", "+919876543210")
    speech = payload.get("speech", "")

    if not speech:
        return JSONResponse({"error": "speech string is required"}, status_code=400)

    session = session_manager.get_or_create(call_sid=call_sid, customer_phone=phone)

    if not config.ENABLE_LLM_AGENT:
        reply = f"Aapne kaha: {speech}"
        session.add_user_message(speech)
        session.add_assistant_message(reply)
    else:
        reply = await agent.run_voice_agent(session=session, customer_speech=speech)

    return {
        "call_sid": call_sid,
        "customer_phone": phone,
        "customer_speech": speech,
        "agent_spoken_reply": reply,
        "llm_agent_enabled": config.ENABLE_LLM_AGENT,
        "session_turns": session.turn_count
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("phonecall.main:app", host=config.HOST, port=config.PORT, reload=True)
