"""
Automated Test Suite for Phone Call Voice Channel.

Tests:
1. / (Health check)
2. /voice (Twilio incoming call webhook + TwiML generation)
3. /process-speech (Basic flow without LLM: transcript echo + Gather loop)
4. /process-speech (Silence handling)
5. Session management continuity
6. Backend REST tools with mocked responses
7. Clean voice output formatting (stripping markdown/emojis)
"""

import pytest
from starlette.testclient import TestClient
from unittest.mock import patch, AsyncMock, MagicMock
import httpx

from phonecall.main import app
from phonecall import config
from phonecall.phone_session import session_manager
from phonecall import tools
from phonecall.agent import clean_for_voice

client = TestClient(app)


def test_health_check():
    """Verify health check endpoint returns 200 and online status."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert data["service"] == "Phone Call Voice Channel"
    assert "twilio_webhooks" in data


def test_incoming_call_twiml():
    """Verify /voice endpoint generates valid TwiML with <Say> and <Gather>."""
    response = client.post(
        "/voice",
        data={"CallSid": "CA_TEST_001", "From": "+919876543210"}
    )
    assert response.status_code == 200
    assert "application/xml" in response.headers["content-type"]
    xml_content = response.text

    # Must contain TwiML tags
    assert "<Response>" in xml_content
    assert "<Gather" in xml_content
    assert 'action="/process-speech"' in xml_content
    assert 'language="hi-IN"' in xml_content
    assert config.DEFAULT_GREETING in xml_content


def test_basic_voice_flow_echo():
    """
    Verify Phase 1 Requirement:
    Basic Twilio voice flow WITHOUT LLM:
    incoming call -> greeting -> Gather speech -> print transcript -> Say transcript.
    """
    # Temporarily force ENABLE_LLM_AGENT = False
    original_flag = config.ENABLE_LLM_AGENT
    config.ENABLE_LLM_AGENT = False

    try:
        call_sid = "CA_TEST_ECHO_001"
        test_speech = "bhaiya do packet maggi aur ek atta dena"

        response = client.post(
            "/process-speech",
            data={
                "CallSid": call_sid,
                "From": "+919876543210",
                "SpeechResult": test_speech,
                "Confidence": "0.95"
            }
        )

        assert response.status_code == 200
        assert "application/xml" in response.headers["content-type"]
        xml_content = response.text

        # Must echo back customer transcript
        assert f"Aapne kaha: {test_speech}" in xml_content
        # Must maintain loop with next <Gather>
        assert "<Gather" in xml_content
        assert 'action="/process-speech"' in xml_content

        # Verify session state was recorded
        session = session_manager.get(call_sid)
        assert session is not None
        assert session.turn_count >= 1

    finally:
        config.ENABLE_LLM_AGENT = original_flag


def test_process_speech_silence():
    """Verify handling when caller remains silent (empty SpeechResult)."""
    response = client.post(
        "/process-speech",
        data={
            "CallSid": "CA_TEST_SILENCE",
            "From": "+919876543210",
            "SpeechResult": ""
        }
    )
    assert response.status_code == 200
    xml_content = response.text
    assert config.SILENCE_PROMPT in xml_content
    assert "<Gather" in xml_content


def test_clean_for_voice():
    """Verify text cleaner removes markdown symbols, bullets, and emojis for TTS."""
    dirty_text = "Here is your order:\n* **Aashirvaad Atta**: Rs. 55\n# Total: Rs. 110! 🛒"
    cleaned = clean_for_voice(dirty_text)
    assert "*" not in cleaned
    assert "**" not in cleaned
    assert "#" not in cleaned
    assert "🛒" not in cleaned
    assert "Aashirvaad Atta: Rs. 55" in cleaned
    assert "Total: Rs. 110!" in cleaned


def test_tools_search_product_mock():
    """Verify search_product calls the REST backend contract."""
    async def _run():
        mock_products = {
            "products": [
                {"id": 101, "name": "Aashirvaad Atta 5kg", "price": 260, "stock": 15}
            ]
        }

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_products
            mock_get.return_value = mock_response

            result = await tools.search_product("atta")
            assert "products" in result
            assert len(result["products"]) == 1
            assert result["products"][0]["name"] == "Aashirvaad Atta 5kg"

    import asyncio
    asyncio.run(_run())


def test_tools_create_order_mock():
    """Verify create_order calls POST /api/orders on the shared backend."""
    async def _run():
        mock_order_response = {
            "order_id": "ORD-9999",
            "status": "confirmed",
            "total": 520,
            "items": [
                {"product_id": 101, "quantity": 2, "name": "Aashirvaad Atta 5kg"}
            ]
        }

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_order_response
            mock_post.return_value = mock_response

            order = await tools.create_order(
                customer_phone="+919876543210",
                items=[{"product_id": 101, "quantity": 2}]
            )
            assert order["order_id"] == "ORD-9999"
            assert order["status"] == "confirmed"
            assert order["total"] == 520

    import asyncio
    asyncio.run(_run())


def test_call_status_termination():
    """Verify call completion removes session from memory."""
    call_sid = "CA_TEST_TERM"
    session_manager.get_or_create(call_sid, "+919876543210")
    assert session_manager.get(call_sid) is not None

    response = client.post(
        "/call-status",
        data={"CallSid": call_sid, "CallStatus": "completed"}
    )
    assert response.status_code == 200
    assert session_manager.get(call_sid) is None


def test_developer_simulation_endpoint():
    """Verify /test-call endpoint allows simulating conversation turns via JSON."""
    response = client.post(
        "/test-call",
        json={
            "call_sid": "DEV_TEST_JSON_01",
            "phone": "+919876543210",
            "speech": "bhaiya namaste kaise ho"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["call_sid"] == "DEV_TEST_JSON_01"
    assert "agent_spoken_reply" in data
    assert len(data["agent_spoken_reply"]) > 0
    assert data["session_turns"] == 1


def test_session_multi_turn():
    """Verify session maintains conversation state across multiple turns."""
    sid = "CA_MULTI_TURN_01"
    sess = session_manager.get_or_create(sid, "+919876543210")
    assert sess.turn_count == 0

    sess.add_user_message("bhaiya 2 atta dena")
    sess.add_assistant_message("Haanji bhaiya, kaunsa atta chahiye?")
    assert sess.turn_count == 1
    assert len(sess.messages) == 2

    sess.add_user_message("Aashirvaad 5kg wala")
    sess.add_assistant_message("Ho gaya bhaiya, order add kar diya.")
    assert sess.turn_count == 2
    assert len(sess.messages) == 4


def test_tools_check_inventory_mock():
    """Verify check_inventory calls GET /api/products/{id} on the backend."""
    async def _run():
        mock_product = {"id": 123, "name": "Aashirvaad Atta 1kg", "price": 55, "stock": 20}

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_product
            mock_get.return_value = mock_response

            res = await tools.check_inventory(123)
            assert res["id"] == 123
            assert res["stock"] == 20
            assert res["price"] == 55

    import asyncio
    asyncio.run(_run())


def test_execute_tool_dispatch():
    """Verify execute_tool correctly routes tool calls to backend functions."""
    async def _run():
        with patch("phonecall.tools.search_product", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = {"products": []}
            await tools.execute_tool("search_product", {"query": "maggi"})
            mock_search.assert_awaited_once_with(query="maggi")

        with patch("phonecall.tools.check_inventory", new_callable=AsyncMock) as mock_check:
            mock_check.return_value = {"stock": 10}
            await tools.execute_tool("check_inventory", {"product_id": 5})
            mock_check.assert_awaited_once_with(product_id=5)

    import asyncio
    asyncio.run(_run())

