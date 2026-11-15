import json
import uuid
import pytest
from unittest.mock import patch, MagicMock
import httpx

from server.database.db import SessionLocal
from server.models.whatsapp_session import WhatsAppCitizen
from server.models.user import User
from server.services.whatsapp_service import WhatsAppService
from server.services.gemini_service import GeminiService, GeminiIntentResult
from server.utils.config import config


@pytest.fixture
def db():
    from server.database.db import Base, engine
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def auth_citizen(db):
    suffix = uuid.uuid4().hex[:8]
    test_phone = f"9197{uuid.uuid4().int % 100000000:08d}"
    user = User(
        full_name="Rajesh Sharma",
        email=f"rajesh_{suffix}@cityswap.io",
        phone=test_phone,
        role="citizen",
        is_active=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    citizen = WhatsAppCitizen(
        phone_number=test_phone,
        full_name="Rajesh Sharma",
        ward="Ward 12",
        is_authorized=True,
        user_id=user.id,
        preferred_language="en",
        eco_coins=150,
        conversation_state="IDLE"
    )
    db.add(citizen)
    db.commit()
    db.refresh(citizen)

    yield citizen

    try:
        db.query(WhatsAppCitizen).filter(WhatsAppCitizen.id == citizen.id).delete()
        db.query(User).filter(User.id == user.id).delete()
        db.commit()
    except Exception:
        db.rollback()


@pytest.fixture
def sent_messages(monkeypatch):
    messages = []

    def capture(to_phone, message_text, buttons=None, interactive=None):
        messages.append({
            "to_phone": to_phone,
            "message_text": message_text,
            "buttons": buttons,
            "interactive": interactive,
        })
        return {"status": "simulated"}

    monkeypatch.setattr(WhatsAppService, "send_meta_whatsapp", staticmethod(capture))
    return messages



def test_gemini_response_parsing_valid_json():
    """Verify that structured JSON outputs from Gemini are correctly parsed."""
    sample_response = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": "```json\n{\n  \"intent\": \"REPORT_WASTE\",\n  \"confidence\": 0.97,\n  \"detected_language\": \"mr\",\n  \"target_language\": null,\n  \"ticket_id\": null,\n  \"contextual_reply\": null\n}\n```"
                        }
                    ]
                }
            }
        ]
    }
    result = GeminiService.parse_gemini_payload(sample_response)
    assert result.intent == "REPORT_WASTE"
    assert result.confidence == 0.97
    assert result.detected_language == "mr"
    assert result.target_language is None
    assert result.is_fallback is False
    assert result.error is None


def test_gemini_response_parsing_invalid_json():
    """Verify that unparseable model output falls back gracefully to UNCLEAR."""
    sample_response = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": "Sorry, I am not able to output valid JSON right now."
                        }
                    ]
                }
            }
        ]
    }
    result = GeminiService.parse_gemini_payload(sample_response)
    assert result.intent == "UNCLEAR"
    assert result.is_fallback is True
    assert "Invalid JSON" in (result.error or "")


def test_gemini_response_parsing_empty_candidates():
    """Verify that an empty or missing candidates response falls back gracefully."""
    empty_response = {"candidates": []}
    result = GeminiService.parse_gemini_payload(empty_response)
    assert result.intent == "UNCLEAR"
    assert result.is_fallback is True
    assert "No candidates" in (result.error or "")


def test_gemini_marathi_intent_classification(db, auth_citizen, sent_messages, monkeypatch):
    """
    When a citizen writes Marathi natural language reporting garbage,
    Gemini classifies it as REPORT_WASTE, transitioning them to AWAITING_PHOTO.
    """
    mock_ai = GeminiIntentResult(
        intent="REPORT_WASTE",
        confidence=0.98,
        detected_language="mr",
        is_fallback=False
    )
    monkeypatch.setattr(GeminiService, "classify_and_respond", lambda *args, **kwargs: mock_ai)

    res = WhatsAppService.handle_incoming_message(
        db, auth_citizen.phone_number, "text", text_body="येथे कचरा साचला आहे कृपया साफ करा"
    )
    assert res["status"] == "awaiting_photo"
    assert res.get("ai_classified") is True
    assert res.get("intent") == "REPORT_WASTE"

    db.refresh(auth_citizen)
    assert auth_citizen.conversation_state == "AWAITING_PHOTO"
    assert len(sent_messages) == 1
    assert "फोटो" in sent_messages[0]["message_text"] or "photo" in sent_messages[0]["message_text"].lower()


def test_gemini_english_intent_classification(db, auth_citizen, sent_messages, monkeypatch):
    """
    When a citizen writes English natural language with a non-waste grievance,
    Gemini classifies it as GENERAL_COMPLAINT, transitioning them to AWAITING_GENERAL_COMPLAINT.
    """
    mock_ai = GeminiIntentResult(
        intent="GENERAL_COMPLAINT",
        confidence=0.95,
        detected_language="en",
        is_fallback=False
    )
    monkeypatch.setattr(GeminiService, "classify_and_respond", lambda *args, **kwargs: mock_ai)

    res = WhatsAppService.handle_incoming_message(
        db, auth_citizen.phone_number, "text", text_body="The street drainage on Sakri Road has been broken for days"
    )
    assert res["status"] == "awaiting_general_complaint"
    assert res.get("ai_classified") is True
    assert res.get("intent") == "GENERAL_COMPLAINT"

    db.refresh(auth_citizen)
    assert auth_citizen.conversation_state == "AWAITING_GENERAL_COMPLAINT"


def test_gemini_mixed_language_intent(db, auth_citizen, sent_messages, monkeypatch):
    """
    When a citizen writes mixed Marathi/English asking to track complaints,
    Gemini classifies it as TRACK_COMPLAINT, returning complaint history.
    """
    mock_ai = GeminiIntentResult(
        intent="TRACK_COMPLAINT",
        confidence=0.94,
        detected_language="mixed",
        is_fallback=False
    )
    monkeypatch.setattr(GeminiService, "classify_and_respond", lambda *args, **kwargs: mock_ai)

    res = WhatsAppService.handle_incoming_message(
        db, auth_citizen.phone_number, "text", text_body="Maza complaint track karaycha ahe please status sanga"
    )
    assert res["status"] == "track_complaints"
    assert res.get("ai_classified") is True
    assert res.get("intent") == "TRACK_COMPLAINT"


def test_gemini_municipal_faq_returns_contextual_answer_with_primary_buttons(db, auth_citizen, sent_messages, monkeypatch):
    """
    When a citizen asks an informational municipal question, Gemini provides
    a grounded civic response accompanied by the 3 primary interactive buttons.
    """
    faq_answer = "Dhule Municipal Corporation offers ₹25 property tax rebate for every 50 EcoCoins earned by reporting waste."
    mock_ai = GeminiIntentResult(
        intent="MUNICIPAL_FAQ",
        confidence=0.96,
        detected_language="en",
        contextual_reply=faq_answer,
        is_fallback=False
    )
    monkeypatch.setattr(GeminiService, "classify_and_respond", lambda *args, **kwargs: mock_ai)

    res = WhatsAppService.handle_incoming_message(
        db, auth_citizen.phone_number, "text", text_body="How can I use my EcoCoins for tax rebate?"
    )
    assert res["status"] == "faq_answered"
    assert res["reply"] == faq_answer
    assert res.get("ai_classified") is True

    # Verified 3 primary buttons are sent with the contextual FAQ answer
    assert len(sent_messages) == 1
    interactive = sent_messages[0]["interactive"]
    assert interactive["type"] == "button"
    button_ids = [b["reply"]["id"] for b in interactive["action"]["buttons"]]
    assert "REPORT_WASTE" in button_ids
    assert "GENERAL_COMPLAINT" in button_ids
    assert "OPEN_FULL_MENU" in button_ids


def test_gemini_ambiguous_request_clarifies_with_primary_buttons(db, auth_citizen, sent_messages, monkeypatch):
    """
    When a citizen's request is ambiguous or unclear, Gemini returns a polite
    clarification accompanied by the 3 primary interactive buttons.
    """
    clarification = "I couldn't quite understand your request. Would you like to report waste or raise a municipal issue?"
    mock_ai = GeminiIntentResult(
        intent="UNCLEAR",
        confidence=0.40,
        detected_language="en",
        contextual_reply=clarification,
        is_fallback=False
    )
    monkeypatch.setattr(GeminiService, "classify_and_respond", lambda *args, **kwargs: mock_ai)

    res = WhatsAppService.handle_incoming_message(
        db, auth_citizen.phone_number, "text", text_body="kahi tari problem zala ahe"
    )
    assert res["status"] == "unclear_clarified"
    assert res["reply"] == clarification

    assert len(sent_messages) == 1
    interactive = sent_messages[0]["interactive"]
    assert interactive["type"] == "button"
    button_ids = [b["reply"]["id"] for b in interactive["action"]["buttons"]]
    assert "REPORT_WASTE" in button_ids
    assert "GENERAL_COMPLAINT" in button_ids
    assert "OPEN_FULL_MENU" in button_ids


def test_gemini_timeout_fallback_to_deterministic_menu(db, auth_citizen, sent_messages, monkeypatch):
    """
    When Gemini API times out, the service catches TimeoutException and falls back
    to the deterministic main menu with feedback, preventing user-facing failure.
    """
    def raise_timeout(*args, **kwargs):
        raise httpx.TimeoutException("Connection timed out")

    monkeypatch.setattr(config, "GEMINI_API_KEY", "mock-test-gemini-key")
    monkeypatch.setattr(httpx.Client, "post", raise_timeout)

    res = WhatsAppService.handle_incoming_message(
        db, auth_citizen.phone_number, "text", text_body="random text that causes timeout"
    )
    assert res["status"] == "menu_presented"
    assert "Unrecognized option" in res["reply"] or "पर्याय उपलब्ध नाही" in res["reply"]

    # Citizen receives the standard primary buttons
    assert len(sent_messages) == 1
    assert sent_messages[0]["interactive"]["type"] == "button"


def test_gemini_http_error_fallback_to_deterministic_menu(db, auth_citizen, sent_messages, monkeypatch):
    """
    When Gemini API returns an HTTP error (e.g. 500, 429), it falls back gracefully
    to the deterministic main menu without exposing raw errors to the citizen.
    """
    def raise_http_error(*args, **kwargs):
        req = httpx.Request("POST", "https://generativelanguage.googleapis.com/")
        resp = httpx.Response(500, request=req)
        raise httpx.HTTPStatusError("Internal Server Error", request=req, response=resp)

    monkeypatch.setattr(config, "GEMINI_API_KEY", "mock-test-gemini-key")
    monkeypatch.setattr(httpx.Client, "post", raise_http_error)

    res = WhatsAppService.handle_incoming_message(
        db, auth_citizen.phone_number, "text", text_body="random text that triggers http error"
    )
    assert res["status"] == "menu_presented"
    assert len(sent_messages) == 1
    assert sent_messages[0]["interactive"]["type"] == "button"


def test_gemini_unconfigured_api_key_falls_back_cleanly(db, auth_citizen, sent_messages, monkeypatch):
    """
    When GEMINI_API_KEY is not configured or empty, classification returns
    fallback without attempting any outbound network call.
    """
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")

    network_called = False
    def trap_network(*args, **kwargs):
        nonlocal network_called
        network_called = True
        raise RuntimeError("Should not be called")

    monkeypatch.setattr(httpx.Client, "post", trap_network)

    res = WhatsAppService.handle_incoming_message(
        db, auth_citizen.phone_number, "text", text_body="unrecognized command with no api key"
    )
    assert network_called is False
    assert res["status"] == "menu_presented"
    assert len(sent_messages) == 1


def test_active_workflows_bypass_gemini_entirely(db, auth_citizen, sent_messages, monkeypatch):
    """
    When a citizen is inside an active workflow (AWAITING_PHOTO, AWAITING_LOCATION,
    AWAITING_GENERAL_COMPLAINT, AWAITING_EVENT_*), Gemini is NEVER invoked.
    """
    gemini_called = False
    def trap_gemini(*args, **kwargs):
        nonlocal gemini_called
        gemini_called = True
        return GeminiIntentResult(intent="UNCLEAR")

    monkeypatch.setattr(GeminiService, "classify_and_respond", trap_gemini)

    # 1. In AWAITING_PHOTO state: sending text repeats the photo prompt
    auth_citizen.conversation_state = "AWAITING_PHOTO"
    db.commit()

    res_photo = WhatsAppService.handle_incoming_message(
        db, auth_citizen.phone_number, "text", text_body="Where should I send it?"
    )
    assert gemini_called is False
    assert res_photo["status"] == "awaiting_photo"

    # 2. In AWAITING_LOCATION state: sending text captures manual address
    auth_citizen.conversation_state = "AWAITING_LOCATION"
    auth_citizen.pending_complaint_data = json.dumps({
        "flow": "waste",
        "image_url": "https://example.com/test.jpg",
        "waste_type": "Mixed Waste"
    })
    db.commit()

    res_loc = WhatsAppService.handle_incoming_message(
        db, auth_citizen.phone_number, "text", text_body="Address: Near Railway Station, Dhule"
    )
    assert gemini_called is False
    assert res_loc["status"] == "complaint_created"

    # 3. In AWAITING_GENERAL_COMPLAINT state: sending text logs the complaint
    auth_citizen.conversation_state = "AWAITING_GENERAL_COMPLAINT"
    db.commit()

    res_gen = WhatsAppService.handle_incoming_message(
        db, auth_citizen.phone_number, "text", text_body="The tap in the municipal park is leaking"
    )
    assert gemini_called is False
    assert res_gen["status"] == "awaiting_general_complaint"

    # 4. In AWAITING_EVENT_DATE state: sending date parses the date
    auth_citizen.conversation_state = "AWAITING_EVENT_DATE"
    auth_citizen.pending_complaint_data = json.dumps({"category": "PUBLIC"})
    db.commit()

    res_evt = WhatsAppService.handle_incoming_message(
        db, auth_citizen.phone_number, "text", text_body="25/12/2026"
    )
    assert gemini_called is False
    assert res_evt["status"] == "awaiting_event_time"


def test_gemini_api_key_not_exposed_in_logs_or_errors():
    """Verify that sanitize_error_message redacts ?key=... in any error or URL string."""
    leaked_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=AIzaSySecretKey123456789"
    sanitized = GeminiService._sanitize_error_message(leaked_url)
    assert "AIzaSySecretKey123456789" not in sanitized
    assert "key=[REDACTED]" in sanitized
