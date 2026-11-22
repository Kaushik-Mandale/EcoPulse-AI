"""
EcoPulse AI — Phase 2 Multilingual Conversational Intelligence Tests.
Validates end-to-end conversation flows, Scenarios A through F, session concurrency,
workflow preservation, idempotency, and template rendering.
"""
import json
import uuid
import pytest
from unittest.mock import patch, MagicMock

from server.database.db import SessionLocal
from server.models.whatsapp_session import WhatsAppCitizen, WhatsAppProcessedMessage
from server.models.user import User
from server.models.complaint import Complaint
from server.services.whatsapp_service import WhatsAppService
from server.services.gemini_service import GeminiService, GeminiIntentResult
from server.services.whatsapp_templates import WhatsAppTemplates
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


def _create_test_citizen(db, preferred_language=None, conversation_state="IDLE", is_authorized=True):
    suffix = uuid.uuid4().hex[:8]
    test_phone = f"9198{uuid.uuid4().int % 100000000:08d}"
    user = User(
        full_name="Vijay Patil",
        email=f"vijay_{suffix}@cityswap.io",
        phone=test_phone,
        role="citizen",
        is_active=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    citizen = WhatsAppCitizen(
        phone_number=test_phone,
        full_name="Vijay Patil",
        ward="Ward 5",
        is_authorized=is_authorized,
        user_id=user.id if is_authorized else None,
        preferred_language=preferred_language,
        eco_coins=100,
        conversation_state=conversation_state
    )
    db.add(citizen)
    db.commit()
    db.refresh(citizen)
    return citizen, user


# =========================================================================
# Scenario A: Hello -> Language Prompt -> English -> English Welcome Menu
# =========================================================================
def test_scenario_a_english_onboarding(db, sent_messages):
    citizen, _ = _create_test_citizen(db, preferred_language=None, conversation_state="IDLE")

    # Step 1: Citizen says "Hello"
    res1 = WhatsAppService.handle_incoming_message(db, citizen.phone_number, "text", text_body="Hello")
    assert res1["status"] == "awaiting_language"
    assert "English" in res1["reply"] or "language" in res1["reply"].lower()
    assert len(sent_messages) == 1
    buttons1 = [b["reply"]["id"] for b in sent_messages[0]["interactive"]["action"]["buttons"]]
    assert "LANG_EN" in buttons1
    assert "LANG_MR" in buttons1

    # Step 2: Citizen chooses "English"
    sent_messages.clear()
    res2 = WhatsAppService.handle_incoming_message(db, citizen.phone_number, "text", text_body="English")
    assert res2["status"] == "language_selected"
    assert res2["language"] == "en"

    db.refresh(citizen)
    assert citizen.preferred_language == "en"
    assert citizen.conversation_state == "IDLE"
    assert len(sent_messages) == 1
    assert "Report Waste" in sent_messages[0]["message_text"]


# =========================================================================
# Scenario B: नमस्कार -> Language Prompt -> मराठी -> Marathi Welcome Menu
# =========================================================================
def test_scenario_b_marathi_onboarding(db, sent_messages):
    citizen, _ = _create_test_citizen(db, preferred_language=None, conversation_state="IDLE")

    # Step 1: Citizen says "नमस्कार"
    res1 = WhatsAppService.handle_incoming_message(db, citizen.phone_number, "text", text_body="नमस्कार")
    assert res1["status"] == "awaiting_language"
    assert "पसंतीची भाषा" in res1["reply"] or "निवडा" in res1["reply"]
    assert len(sent_messages) == 1

    # Step 2: Citizen chooses "मराठी"
    sent_messages.clear()
    res2 = WhatsAppService.handle_incoming_message(db, citizen.phone_number, "text", text_body="मराठी")
    assert res2["status"] == "language_selected"
    assert res2["language"] == "mr"

    db.refresh(citizen)
    assert citizen.preferred_language == "mr"
    assert citizen.conversation_state == "IDLE"
    assert len(sent_messages) == 1
    assert "कचरा नोंदवा" in sent_messages[0]["message_text"]


# =========================================================================
# Scenario C: "I want to report garbage" -> starts waste reporting workflow
# =========================================================================
def test_scenario_c_report_garbage_english(db, sent_messages, monkeypatch):
    citizen, _ = _create_test_citizen(db, preferred_language="en", conversation_state="IDLE")

    mock_gemini = GeminiIntentResult(
        intent="REPORT_WASTE",
        confidence=0.98,
        detected_language="en",
        is_fallback=False
    )
    monkeypatch.setattr(GeminiService, "classify_and_respond", lambda *args, **kwargs: mock_gemini)

    res = WhatsAppService.handle_incoming_message(
        db, citizen.phone_number, "text", text_body="I want to report garbage"
    )
    assert res["status"] == "awaiting_photo"
    assert res.get("ai_classified") is True
    assert res.get("intent") == "REPORT_WASTE"

    db.refresh(citizen)
    assert citizen.conversation_state == "AWAITING_PHOTO"
    assert len(sent_messages) == 1
    assert "photo" in sent_messages[0]["message_text"].lower()


# =========================================================================
# Scenario D: "कचरा उचलला नाही" -> understands complaint and starts workflow
# =========================================================================
def test_scenario_d_garbage_not_collected_marathi(db, sent_messages, monkeypatch):
    citizen, _ = _create_test_citizen(db, preferred_language="mr", conversation_state="IDLE")

    mock_gemini = GeminiIntentResult(
        intent="GARBAGE_NOT_COLLECTED",
        confidence=0.97,
        detected_language="mr",
        is_fallback=False
    )
    monkeypatch.setattr(GeminiService, "classify_and_respond", lambda *args, **kwargs: mock_gemini)

    res = WhatsAppService.handle_incoming_message(
        db, citizen.phone_number, "text", text_body="कचरा उचलला नाही"
    )
    assert res["status"] == "awaiting_photo"
    assert res.get("ai_classified") is True
    assert res.get("intent") == "GARBAGE_NOT_COLLECTED"

    db.refresh(citizen)
    assert citizen.conversation_state == "AWAITING_PHOTO"
    assert len(sent_messages) == 1
    assert "फोटो पाठवा" in sent_messages[0]["message_text"]


# =========================================================================
# Scenario E: "Thank you" -> Localized Gratitude Response
# =========================================================================
def test_scenario_e_thank_you_gratitude(db, sent_messages, monkeypatch):
    citizen, _ = _create_test_citizen(db, preferred_language="en", conversation_state="IDLE")

    mock_gemini = GeminiIntentResult(
        intent="GRATITUDE",
        confidence=0.99,
        detected_language="en",
        is_fallback=False
    )
    monkeypatch.setattr(GeminiService, "classify_and_respond", lambda *args, **kwargs: mock_gemini)

    res = WhatsAppService.handle_incoming_message(
        db, citizen.phone_number, "text", text_body="Thank you so much!"
    )
    assert res["status"] == "gratitude_acknowledged"
    assert res.get("ai_classified") is True
    assert res.get("intent") == "GRATITUDE"

    assert len(sent_messages) == 1
    assert "welcome" in sent_messages[0]["message_text"].lower()


def test_scenario_e_marathi_dhanyavad(db, sent_messages, monkeypatch):
    citizen, _ = _create_test_citizen(db, preferred_language="mr", conversation_state="IDLE")

    mock_gemini = GeminiIntentResult(
        intent="GRATITUDE",
        confidence=0.99,
        detected_language="mr",
        is_fallback=False
    )
    monkeypatch.setattr(GeminiService, "classify_and_respond", lambda *args, **kwargs: mock_gemini)

    res = WhatsAppService.handle_incoming_message(
        db, citizen.phone_number, "text", text_body="धन्यवाद"
    )
    assert res["status"] == "gratitude_acknowledged"
    assert len(sent_messages) == 1
    assert "धन्यवाद" in sent_messages[0]["message_text"]


# =========================================================================
# Scenario F: "Can I change my language?" -> Prompts Language Selection
# Preserves active complaint info without clearing it
# =========================================================================
def test_scenario_f_change_language_preserves_context(db, sent_messages, monkeypatch):
    citizen, _ = _create_test_citizen(db, preferred_language="mr", conversation_state="IDLE")

    # Citizen has some complaint data in progress
    pending_payload = json.dumps({"waste_type": "Plastic", "draft": True})
    citizen.pending_complaint_data = pending_payload
    db.commit()

    mock_gemini = GeminiIntentResult(
        intent="CHANGE_LANGUAGE",
        confidence=0.96,
        detected_language="en",
        target_language=None,
        is_fallback=False
    )
    monkeypatch.setattr(GeminiService, "classify_and_respond", lambda *args, **kwargs: mock_gemini)

    res = WhatsAppService.handle_incoming_message(
        db, citizen.phone_number, "text", text_body="Can I change my language?"
    )
    assert res["status"] == "awaiting_language"
    assert res.get("ai_classified") is True

    db.refresh(citizen)
    assert citizen.conversation_state == "AWAITING_LANGUAGE"
    # Verify pending data is NOT deleted!
    assert citizen.pending_complaint_data == pending_payload
    assert len(sent_messages) == 1


# =========================================================================
# Collection Schedule Intent ("उद्या कचरा कधी येणार?")
# =========================================================================
def test_collection_schedule_marathi(db, sent_messages, monkeypatch):
    citizen, _ = _create_test_citizen(db, preferred_language="mr", conversation_state="IDLE")

    mock_gemini = GeminiIntentResult(
        intent="COLLECTION_SCHEDULE",
        confidence=0.95,
        detected_language="mr",
        is_fallback=False
    )
    monkeypatch.setattr(GeminiService, "classify_and_respond", lambda *args, **kwargs: mock_gemini)

    res = WhatsAppService.handle_incoming_message(
        db, citizen.phone_number, "text", text_body="उद्या कचरा कधी येणार?"
    )
    assert res["status"] == "collection_schedule"
    assert res.get("ai_classified") is True

    assert len(sent_messages) == 1
    assert "वेळापत्रक" in sent_messages[0]["message_text"]


# =========================================================================
# General Complaint Intent ("मला तक्रार करायची आहे")
# =========================================================================
def test_general_complaint_marathi(db, sent_messages, monkeypatch):
    citizen, _ = _create_test_citizen(db, preferred_language="mr", conversation_state="IDLE")

    mock_gemini = GeminiIntentResult(
        intent="GENERAL_COMPLAINT",
        confidence=0.96,
        detected_language="mr",
        is_fallback=False
    )
    monkeypatch.setattr(GeminiService, "classify_and_respond", lambda *args, **kwargs: mock_gemini)

    res = WhatsAppService.handle_incoming_message(
        db, citizen.phone_number, "text", text_body="मला तक्रार करायची आहे"
    )
    assert res["status"] == "awaiting_general_complaint"
    assert res.get("ai_classified") is True

    db.refresh(citizen)
    assert citizen.conversation_state == "AWAITING_GENERAL_COMPLAINT"


# =========================================================================
# Concurrent Sessions Isolation
# =========================================================================
def test_concurrent_citizen_sessions_isolated(db, sent_messages):
    citizen_a, _ = _create_test_citizen(db, preferred_language="en", conversation_state="IDLE")
    citizen_b, _ = _create_test_citizen(db, preferred_language="mr", conversation_state="IDLE")

    # Citizen A starts waste flow
    res_a = WhatsAppService.handle_incoming_message(db, citizen_a.phone_number, "text", text_body="1")
    assert res_a["status"] == "awaiting_photo"

    # Citizen B sends "5" (EcoWallet)
    res_b = WhatsAppService.handle_incoming_message(db, citizen_b.phone_number, "text", text_body="5")
    assert res_b["status"] == "wallet_info"

    # Verify states remain isolated
    db.refresh(citizen_a)
    db.refresh(citizen_b)
    assert citizen_a.conversation_state == "AWAITING_PHOTO"
    assert citizen_a.preferred_language == "en"

    assert citizen_b.conversation_state == "IDLE"
    assert citizen_b.preferred_language == "mr"


# =========================================================================
# Webhook Event Idempotency (Duplicate Prevention)
# =========================================================================
def test_duplicate_webhook_message_id_idempotency(db, sent_messages, monkeypatch):
    import hmac
    import hashlib
    from fastapi.testclient import TestClient
    from server.main import app

    test_secret = "test_meta_webhook_secret_key"
    monkeypatch.setattr(config, "META_APP_SECRET", test_secret)

    client = TestClient(app)
    citizen, _ = _create_test_citizen(db, preferred_language="en", conversation_state="IDLE")
    test_msg_id = f"wamid.{uuid.uuid4().hex}"

    webhook_payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "104829104829104",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"display_phone_number": "15550234567", "phone_number_id": "104829104829104"},
                    "messages": [{
                        "from": citizen.phone_number,
                        "id": test_msg_id,
                        "timestamp": "1710000400",
                        "type": "text",
                        "text": {"body": "MENU_FULL_MENU"}
                    }]
                },
                "field": "messages"
            }]
        }]
    }

    raw_bytes = json.dumps(webhook_payload).encode("utf-8")
    sig = "sha256=" + hmac.new(test_secret.encode("utf-8"), raw_bytes, hashlib.sha256).hexdigest()
    headers = {"Content-Type": "application/json", "X-Hub-Signature-256": sig}

    # First delivery: processed successfully (HTTP 200)
    resp1 = client.post("/api/whatsapp/webhook", content=raw_bytes, headers=headers)
    assert resp1.status_code == 200
    assert len(sent_messages) == 1

    # Second delivery with the EXACT same message_id: route checks WhatsAppProcessedMessage and skips duplicate!
    sent_messages.clear()
    resp2 = client.post("/api/whatsapp/webhook", content=raw_bytes, headers=headers)
    assert resp2.status_code == 200
    assert len(sent_messages) == 0  # No duplicate message sent!


# =========================================================================
# Centralized Templates Module Completeness
# =========================================================================
def test_whatsapp_templates_contain_all_required_categories():
    all_texts = WhatsAppTemplates.build_all_texts()
    assert "mr" in all_texts
    assert "en" in all_texts

    required_keys = [
        "unauthorized", "not_linked_prompt", "authorized_welcome", "linked_welcome",
        "menu_options", "ask_photo", "photo_received_ack", "ask_location",
        "invalid_location", "report_success", "complaint_created", "general_complaint_prompt",
        "general_complaint_received", "no_complaints", "complaints_header",
        "driver_assignment_update", "collection_schedule", "wallet_info",
        "municipal_notices", "help_text", "thank_you", "confirmation",
        "unrecognized_option", "link_prompt", "link_invalid", "event_category_prompt"
    ]

    for lang in ["mr", "en"]:
        for key in required_keys:
            assert key in all_texts[lang], f"Missing required template key: {key} in lang {lang}"
            assert len(all_texts[lang][key]) > 0
