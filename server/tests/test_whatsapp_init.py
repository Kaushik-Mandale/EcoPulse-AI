"""
WhatsApp Conversation Initialization Tests
===========================================
Verifies the corrected language gate execution order specification:

1. Language Selection executes BEFORE citizen authorization:
   - Every new user (no preferred_language) must receive language selection first,
     regardless of what first message they send (hello, arbitrary text, greetings).
   - An unlinked citizen can select a language, but after selecting language they receive
     the existing authorization response (not_linked_prompt) and are prevented from
     accessing protected services.
2. QR Onboarding corrections:
   - Valid QR JOIN saves household ID and ward and sets is_authorized=True.
   - Does NOT automatically assign Marathi (preferred_language remains None).
   - Sends the language selector rather than the normal authorized welcome menu.
   - Selecting English after QR JOIN persists 'en' and sends the approved English welcome.
   - Selecting Marathi after QR JOIN persists 'mr' and sends the approved Marathi welcome.
3. Existing functionality preserved:
   - Existing linked citizens with saved language continue working normally.
   - Existing active conversation workflows (AWAITING_PHOTO, AWAITING_LOCATION, etc.)
     are not interrupted by the language gate.
   - Explicit START / LANG / LANGUAGE always reopen language selection.
   - Full Menu sends all eight options separately.
   - Gemini is never called during the language-selection gate.
"""
import uuid
import pytest
from unittest.mock import patch, MagicMock
from server.database.db import SessionLocal
from server.models.whatsapp_session import WhatsAppCitizen
from server.models.user import User
from server.services.whatsapp_service import WhatsAppService


# ─────────────────────────────────────────────
# Shared fixtures
# ─────────────────────────────────────────────

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
    """Capture all outbound WhatsApp messages sent during the test (matches existing pattern)."""
    messages = []

    def capture(to_phone, message_text="", buttons=None, interactive=None):
        messages.append({
            "to_phone": to_phone,
            "message_text": message_text,
            "buttons": buttons,
            "interactive": interactive,
        })
        return {"status": "simulated"}

    monkeypatch.setattr(WhatsAppService, "send_meta_whatsapp", staticmethod(capture))
    monkeypatch.setattr(WhatsAppService, "send_meta_location_request", staticmethod(capture))
    return messages


def _make_new_citizen(db, *, household_id=None, preferred_language=None,
                       conversation_state="IDLE", is_authorized=True):
    """Create a fresh linked citizen record for initialization tests."""
    suffix = uuid.uuid4().hex[:8]
    phone = f"9197{uuid.uuid4().int % 100000000:08d}"

    user_obj = User(
        full_name="Test Citizen",
        email=f"init_test_{suffix}@cityswap.io",
        phone=phone,
        role="citizen",
        is_active=True,
    )
    db.add(user_obj)
    db.commit()
    db.refresh(user_obj)

    citizen = WhatsAppCitizen(
        phone_number=phone,
        full_name="Test Citizen",
        ward="Ward 3",
        household_id=household_id,
        is_authorized=is_authorized,
        user_id=user_obj.id,
        preferred_language=preferred_language,
        eco_coins=0,
        conversation_state=conversation_state,
    )
    db.add(citizen)
    db.commit()
    db.refresh(citizen)
    return citizen, user_obj


def _make_unlinked_citizen(db, *, preferred_language=None, conversation_state="IDLE"):
    """Create a fresh UNLINKED citizen record (no user_id, is_authorized=False)."""
    phone = f"9196{uuid.uuid4().int % 100000000:08d}"
    citizen = WhatsAppCitizen(
        phone_number=phone,
        full_name="Dhule Citizen",
        ward=None,
        household_id=None,
        is_authorized=False,
        user_id=None,
        preferred_language=preferred_language,
        eco_coins=0,
        conversation_state=conversation_state,
    )
    db.add(citizen)
    db.commit()
    db.refresh(citizen)
    return citizen


def _cleanup(db, citizen, user=None):
    try:
        db.query(WhatsAppCitizen).filter(WhatsAppCitizen.id == citizen.id).delete()
        if user:
            db.query(User).filter(User.id == user.id).delete()
        db.commit()
    except Exception:
        db.rollback()


# ─────────────────────────────────────────────
# 1. First-message → language selection gate (Linked Citizen)
# ─────────────────────────────────────────────

@pytest.mark.parametrize("first_msg", [
    "hey", "hii", "hello", "yoo", "yo", "START", "start",
    "good morning", "random arbitrary text",
    "English", "english", "Marathi", "marathi", "मराठी",
    "नमस्कार", "कचरा",         # Marathi first message
    "👋",                      # emoji-only
])
def test_every_first_message_triggers_language_selection(db, sent_messages, first_msg):
    """
    Every incoming message from a citizen with no preferred_language must
    trigger the bilingual language-selection prompt, not a greeting or menu.
    """
    citizen, user = _make_new_citizen(db, preferred_language=None, conversation_state="IDLE")
    try:
        res = WhatsAppService.handle_incoming_message(
            db, citizen.phone_number, "text", text_body=first_msg
        )
        assert res["status"] == "awaiting_language", (
            f"Expected 'awaiting_language' for first_msg={first_msg!r}, got {res['status']!r}"
        )
        assert len(sent_messages) == 1, (
            f"Expected exactly 1 message for first_msg={first_msg!r}, got {len(sent_messages)}"
        )
        interactive = sent_messages[0]["interactive"]
        assert interactive is not None, f"Expected interactive payload for {first_msg!r}"
        assert interactive["type"] == "button"
        button_ids = [b["reply"]["id"] for b in interactive["action"]["buttons"]]
        assert "LANG_EN" in button_ids, f"LANG_EN button missing for {first_msg!r}"
        assert "LANG_MR" in button_ids, f"LANG_MR button missing for {first_msg!r}"

        # Main menu / greeting must NOT appear before language selection
        body = sent_messages[0]["message_text"]
        assert "Report Waste" not in body, (
            f"Menu leaked before language selection for {first_msg!r}: {body[:200]!r}"
        )
    finally:
        _cleanup(db, citizen, user)


# ─────────────────────────────────────────────
# 2. Execution-Order Corrections: Unlinked Citizens & QR Onboarding
# ─────────────────────────────────────────────

def test_new_unlinked_citizen_sending_hello_receives_language_selection_first(db, sent_messages):
    """
    Requirement 1: New unlinked citizen sending hello receives language selection first.
    Language gate must execute before the citizen authorization gate.
    """
    citizen = _make_unlinked_citizen(db, preferred_language=None, conversation_state="IDLE")
    try:
        res = WhatsAppService.handle_incoming_message(
            db, citizen.phone_number, "text", text_body="hello"
        )
        assert res["status"] == "awaiting_language"
        assert len(sent_messages) == 1
        interactive = sent_messages[0]["interactive"]
        assert interactive["type"] == "button"
        button_ids = [b["reply"]["id"] for b in interactive["action"]["buttons"]]
        assert "LANG_EN" in button_ids
        assert "LANG_MR" in button_ids
        # Authorization prompt must NOT be sent before language selection
        assert "LINK <code>" not in sent_messages[0]["message_text"]
    finally:
        _cleanup(db, citizen)


def test_new_unlinked_citizen_sending_arbitrary_text_receives_language_selection_first(db, sent_messages):
    """
    Requirement 2: New unlinked citizen sending arbitrary text receives language selection first.
    """
    citizen = _make_unlinked_citizen(db, preferred_language=None, conversation_state="IDLE")
    try:
        res = WhatsAppService.handle_incoming_message(
            db, citizen.phone_number, "text", text_body="When will the garbage truck arrive?"
        )
        assert res["status"] == "awaiting_language"
        assert len(sent_messages) == 1
        interactive = sent_messages[0]["interactive"]
        assert interactive["type"] == "button"
        button_ids = [b["reply"]["id"] for b in interactive["action"]["buttons"]]
        assert "LANG_EN" in button_ids
        assert "LANG_MR" in button_ids
        assert "LINK <code>" not in sent_messages[0]["message_text"]
    finally:
        _cleanup(db, citizen)


def test_selecting_language_does_not_grant_access_to_unlinked_citizen(db, sent_messages):
    """
    Requirement 3: Selecting a language does not grant access to protected services to an unlinked citizen.
    After language selection, subsequent attempts to invoke services are rejected.
    """
    citizen = _make_unlinked_citizen(db, preferred_language=None, conversation_state="AWAITING_LANGUAGE")
    try:
        # Step 1: Select English
        res = WhatsAppService.handle_incoming_message(
            db, citizen.phone_number, "interactive", text_body="LANG_EN"
        )
        assert res["status"] == "not_linked"
        # Language was saved
        db.refresh(citizen)
        assert citizen.preferred_language == "en"
        assert citizen.conversation_state == "IDLE"

        # Step 2: Attempt to access protected service ("1" / Report Waste)
        sent_messages.clear()
        res_svc = WhatsAppService.handle_incoming_message(
            db, citizen.phone_number, "text", text_body="1"
        )
        assert res_svc["status"] == "not_linked"
        # Must not enter workflow
        db.refresh(citizen)
        assert citizen.conversation_state == "IDLE"
        assert len(sent_messages) == 1
        assert "LINK <code>" in sent_messages[0]["message_text"]
    finally:
        _cleanup(db, citizen)


def test_unlinked_citizen_receives_existing_authorization_response_after_selecting_language(db, sent_messages):
    """
    Requirement 4: Unlinked citizen receives the existing authorization response after selecting a language.
    English selection -> English onboarding prompt with website registration instructions and LINK command.
    Marathi selection -> Marathi onboarding prompt.
    """
    # English selection
    citizen_en = _make_unlinked_citizen(db, preferred_language=None, conversation_state="AWAITING_LANGUAGE")
    try:
        res_en = WhatsAppService.handle_incoming_message(
            db, citizen_en.phone_number, "interactive", text_body="LANG_EN"
        )
        assert res_en["status"] == "not_linked"
        assert res_en["language"] == "en"
        assert len(sent_messages) == 1
        body_en = sent_messages[0]["message_text"]
        assert "Welcome to EcoPulse AI — Dhule Municipal Waste Management" in body_en
        assert "To use this service, please first register as a citizen on the EcoPulse AI website" in body_en
        assert "LINK <code>" in body_en
        assert "1. 🗑️ Report Waste" not in body_en
    finally:
        _cleanup(db, citizen_en)

    # Marathi selection
    sent_messages.clear()
    citizen_mr = _make_unlinked_citizen(db, preferred_language=None, conversation_state="AWAITING_LANGUAGE")
    try:
        res_mr = WhatsAppService.handle_incoming_message(
            db, citizen_mr.phone_number, "interactive", text_body="LANG_MR"
        )
        assert res_mr["status"] == "not_linked"
        assert res_mr["language"] == "mr"
        assert len(sent_messages) == 1
        body_mr = sent_messages[0]["message_text"]
        assert "इकोपल्स AI — धुळे महानगरपालिका स्वच्छता व्यवस्थापन" in body_mr
        assert "ही सेवा वापरण्यासाठी प्रथम EcoPulse AI वेबसाइटवर नागरिक म्हणून नोंदणी करा" in body_mr
        assert "LINK <code>" in body_mr
        assert "1. 🗑️ कचरा नोंदवा" not in body_mr
    finally:
        _cleanup(db, citizen_mr)


def test_valid_qr_join_does_not_automatically_assign_marathi(db, sent_messages):
    """
    Requirement 5: Valid QR JOIN does not automatically assign Marathi.
    Household ID and ward are saved, is_authorized=True, but preferred_language remains None.
    """
    phone = f"9198{uuid.uuid4().int % 100000000:08d}"
    citizen = WhatsAppCitizen(
        phone_number=phone,
        full_name="Dhule Citizen",
        is_authorized=False,
        preferred_language=None,
        conversation_state="IDLE",
    )
    db.add(citizen)
    db.commit()
    try:
        res = WhatsAppService.handle_incoming_message(
            db, phone, "text", text_body="JOIN SHP-W14-H2045"
        )
        db.refresh(citizen)
        assert citizen.household_id == "SHP-W14-H2045"
        assert citizen.ward == "Ward 14"
        assert citizen.is_authorized is True
        assert citizen.preferred_language is None, "preferred_language must NOT be auto-assigned to 'mr'"
    finally:
        _cleanup(db, citizen)


def test_qr_join_sends_language_selector_rather_than_normal_welcome_menu(db, sent_messages):
    """
    Requirement 6: QR JOIN sends the language selector rather than the normal welcome menu.
    """
    phone = f"9198{uuid.uuid4().int % 100000000:08d}"
    citizen = WhatsAppCitizen(
        phone_number=phone,
        full_name="Dhule Citizen",
        is_authorized=False,
        preferred_language=None,
        conversation_state="IDLE",
    )
    db.add(citizen)
    db.commit()
    try:
        res = WhatsAppService.handle_incoming_message(
            db, phone, "text", text_body="JOIN SHP-W14-H2045"
        )
        assert res["status"] == "awaiting_language"
        db.refresh(citizen)
        assert citizen.conversation_state == "AWAITING_LANGUAGE"
        assert len(sent_messages) == 1
        interactive = sent_messages[0]["interactive"]
        assert interactive is not None
        assert interactive["type"] == "button"
        button_ids = [b["reply"]["id"] for b in interactive["action"]["buttons"]]
        assert "LANG_EN" in button_ids
        assert "LANG_MR" in button_ids
        # Normal welcome menu must NOT be sent
        assert "1. 🗑️ Report Waste" not in sent_messages[0]["message_text"]
        assert "1. 🗑️ कचरा नोंदवा" not in sent_messages[0]["message_text"]
    finally:
        _cleanup(db, citizen)


def test_selecting_english_after_qr_join_persists_en_and_sends_english_welcome(db, sent_messages):
    """
    Requirement 7: Selecting English after QR JOIN persists 'en' and sends English welcome.
    Accompanied by exactly three primary buttons: Report Waste, General Complaint, Full Menu.
    """
    phone = f"9198{uuid.uuid4().int % 100000000:08d}"
    citizen = WhatsAppCitizen(
        phone_number=phone,
        full_name="Dhule Citizen",
        is_authorized=False,
        preferred_language=None,
        conversation_state="IDLE",
    )
    db.add(citizen)
    db.commit()
    try:
        # Step 1: Citizen scans QR code
        WhatsAppService.handle_incoming_message(
            db, phone, "text", text_body="JOIN SHP-W14-H2045"
        )
        sent_messages.clear()

        # Step 2: Citizen chooses English
        res = WhatsAppService.handle_incoming_message(
            db, phone, "interactive", text_body="LANG_EN"
        )
        assert res["status"] == "language_selected"
        assert res["language"] == "en"
        db.refresh(citizen)
        assert citizen.preferred_language == "en"
        assert citizen.conversation_state == "IDLE"

        # English welcome template delivered
        assert len(sent_messages) == 1
        interactive = sent_messages[0]["interactive"]
        assert interactive["type"] == "button"
        button_ids = [b["reply"]["id"] for b in interactive["action"]["buttons"]]
        assert "REPORT_WASTE" in button_ids
        assert "GENERAL_COMPLAINT" in button_ids
        assert "OPEN_FULL_MENU" in button_ids
        body = sent_messages[0]["message_text"]
        assert "EcoPulse AI" in body
        assert "Hello" in body
        assert "Report Waste" in body
    finally:
        _cleanup(db, citizen)


def test_selecting_marathi_after_qr_join_persists_mr_and_sends_marathi_welcome(db, sent_messages):
    """
    Requirement 8: Selecting Marathi after QR JOIN persists 'mr' and sends Marathi welcome.
    Accompanied by exactly three primary buttons in Marathi.
    """
    phone = f"9198{uuid.uuid4().int % 100000000:08d}"
    citizen = WhatsAppCitizen(
        phone_number=phone,
        full_name="Dhule Citizen",
        is_authorized=False,
        preferred_language=None,
        conversation_state="IDLE",
    )
    db.add(citizen)
    db.commit()
    try:
        # Step 1: Citizen scans QR code
        WhatsAppService.handle_incoming_message(
            db, phone, "text", text_body="JOIN SHP-W14-H2045"
        )
        sent_messages.clear()

        # Step 2: Citizen chooses Marathi
        res = WhatsAppService.handle_incoming_message(
            db, phone, "interactive", text_body="LANG_MR"
        )
        assert res["status"] == "language_selected"
        assert res["language"] == "mr"
        db.refresh(citizen)
        assert citizen.preferred_language == "mr"
        assert citizen.conversation_state == "IDLE"

        # Marathi welcome template delivered
        assert len(sent_messages) == 1
        interactive = sent_messages[0]["interactive"]
        assert interactive["type"] == "button"
        button_ids = [b["reply"]["id"] for b in interactive["action"]["buttons"]]
        assert "REPORT_WASTE" in button_ids
        assert "GENERAL_COMPLAINT" in button_ids
        assert "OPEN_FULL_MENU" in button_ids
        body = sent_messages[0]["message_text"]
        assert "EcoPulse AI" in body
        assert "नमस्कार" in body
        assert "कचरा नोंदवा" in body
    finally:
        _cleanup(db, citizen)


def test_existing_linked_citizens_with_saved_language_continue_working_normally(db, sent_messages):
    """
    Requirement 9: Existing linked citizens with saved language continue working normally.
    Does not present language selection; delivers menu/quick-action buttons.
    """
    citizen, user = _make_new_citizen(db, preferred_language="en", conversation_state="IDLE", is_authorized=True)
    try:
        res = WhatsAppService.handle_incoming_message(
            db, citizen.phone_number, "text", text_body="hello"
        )
        assert res["status"] == "menu_presented"
        assert len(sent_messages) == 1
        button_ids = [b["reply"]["id"] for b in sent_messages[0]["interactive"]["action"]["buttons"]]
        assert "REPORT_WASTE" in button_ids
        assert "GENERAL_COMPLAINT" in button_ids
        assert "OPEN_FULL_MENU" in button_ids
        assert "LANG_EN" not in button_ids
        assert "LANG_MR" not in button_ids
    finally:
        _cleanup(db, citizen, user)


def test_existing_active_workflows_are_not_interrupted(db, sent_messages):
    """
    Requirement 10: Existing active workflows are not interrupted by the language gate.
    A citizen in AWAITING_PHOTO or AWAITING_LOCATION remains in that workflow.
    """
    citizen, user = _make_new_citizen(db, preferred_language="en", conversation_state="AWAITING_PHOTO", is_authorized=True)
    try:
        res = WhatsAppService.handle_incoming_message(
            db, citizen.phone_number, "text", text_body="Where should I send the photo?"
        )
        assert res["status"] == "awaiting_photo"
        db.refresh(citizen)
        assert citizen.conversation_state == "AWAITING_PHOTO"
    finally:
        _cleanup(db, citizen, user)


# ─────────────────────────────────────────────
# 3. Language Selection & Persistence (Linked Citizen)
# ─────────────────────────────────────────────

def test_english_selection_persists_and_sends_english_welcome(db, sent_messages):
    """
    Selecting English (LANG_EN) persists 'en', sets state=IDLE, and sends English welcome.
    """
    citizen, user = _make_new_citizen(
        db, preferred_language=None, conversation_state="AWAITING_LANGUAGE"
    )
    try:
        res = WhatsAppService.handle_incoming_message(
            db, citizen.phone_number, "interactive", text_body="LANG_EN"
        )
        assert res["status"] == "language_selected"
        assert res["language"] == "en"
        db.refresh(citizen)
        assert citizen.preferred_language == "en"
        assert citizen.conversation_state == "IDLE"

        assert len(sent_messages) == 1
        body = sent_messages[0]["message_text"]
        interactive = sent_messages[0]["interactive"]
        assert "EcoPulse AI" in body
        assert interactive["type"] == "button"
        button_ids = [b["reply"]["id"] for b in interactive["action"]["buttons"]]
        assert "REPORT_WASTE" in button_ids
        assert "GENERAL_COMPLAINT" in button_ids
        assert "OPEN_FULL_MENU" in button_ids
    finally:
        _cleanup(db, citizen, user)


def test_marathi_selection_persists_and_sends_marathi_welcome(db, sent_messages):
    """
    Selecting Marathi (LANG_MR) persists 'mr', sets state=IDLE, and sends Marathi welcome.
    """
    citizen, user = _make_new_citizen(
        db, preferred_language=None, conversation_state="AWAITING_LANGUAGE"
    )
    try:
        res = WhatsAppService.handle_incoming_message(
            db, citizen.phone_number, "interactive", text_body="LANG_MR"
        )
        assert res["status"] == "language_selected"
        assert res["language"] == "mr"
        db.refresh(citizen)
        assert citizen.preferred_language == "mr"
        assert citizen.conversation_state == "IDLE"

        assert len(sent_messages) == 1
        body = sent_messages[0]["message_text"]
        interactive = sent_messages[0]["interactive"]
        assert "EcoPulse AI" in body
        button_ids = [b["reply"]["id"] for b in interactive["action"]["buttons"]]
        assert "REPORT_WASTE" in button_ids
        assert "GENERAL_COMPLAINT" in button_ids
        assert "OPEN_FULL_MENU" in button_ids
    finally:
        _cleanup(db, citizen, user)


def test_no_duplicate_language_prompt_after_selection(db, sent_messages):
    """
    After language selection, the NEXT message must NOT receive another language prompt.
    """
    citizen, user = _make_new_citizen(
        db, preferred_language=None, conversation_state="AWAITING_LANGUAGE"
    )
    try:
        WhatsAppService.handle_incoming_message(
            db, citizen.phone_number, "interactive", text_body="LANG_EN"
        )
        db.refresh(citizen)
        assert citizen.preferred_language == "en"

        sent_messages.clear()
        res2 = WhatsAppService.handle_incoming_message(
            db, citizen.phone_number, "text", text_body="hello"
        )
        assert res2["status"] != "awaiting_language"
        assert len(sent_messages) == 1
        button_ids = [b["reply"]["id"] for b in sent_messages[0]["interactive"]["action"]["buttons"]]
        assert "LANG_EN" not in button_ids
        assert "LANG_MR" not in button_ids
    finally:
        _cleanup(db, citizen, user)


def test_language_selection_survives_across_sessions(db, sent_messages):
    """
    preferred_language saved during selection must persist and be honoured
    in subsequent webhook invocations (simulated DB re-read via db.expire_all).
    """
    citizen, user = _make_new_citizen(
        db, preferred_language=None, conversation_state="AWAITING_LANGUAGE"
    )
    try:
        WhatsAppService.handle_incoming_message(
            db, citizen.phone_number, "interactive", text_body="LANG_EN"
        )
        db.expire_all()
        db.refresh(citizen)
        assert citizen.preferred_language == "en"

        sent_messages.clear()
        res = WhatsAppService.handle_incoming_message(
            db, citizen.phone_number, "text", text_body="hi"
        )
        assert res["status"] != "awaiting_language"
    finally:
        _cleanup(db, citizen, user)


# ─────────────────────────────────────────────
# 4. Returning users
# ─────────────────────────────────────────────

@pytest.mark.parametrize("greeting", [
    "hey", "hello", "hi", "hii", "yoo", "yo", "good morning"
])
def test_returning_user_greetings_bypass_language_gate(db, sent_messages, greeting):
    """
    Returning citizens (preferred_language already saved) sending ANY greeting
    must receive the welcome menu — NOT language selection.
    """
    citizen, user = _make_new_citizen(
        db, preferred_language="en", conversation_state="IDLE"
    )
    try:
        res = WhatsAppService.handle_incoming_message(
            db, citizen.phone_number, "text", text_body=greeting
        )
        assert res["status"] != "awaiting_language"
        assert len(sent_messages) == 1
        button_ids = [b["reply"]["id"] for b in sent_messages[0]["interactive"]["action"]["buttons"]]
        assert "LANG_EN" not in button_ids
        assert "LANG_MR" not in button_ids
        assert "REPORT_WASTE" in button_ids
    finally:
        _cleanup(db, citizen, user)


def test_returning_user_free_text_not_blocked_by_language_gate(db, sent_messages):
    """
    Ordinary free-text from a returning citizen (preferred_language saved)
    must NOT be intercepted by the language gate.
    """
    citizen, user = _make_new_citizen(
        db, preferred_language="en", conversation_state="IDLE"
    )
    try:
        res = WhatsAppService.handle_incoming_message(
            db, citizen.phone_number, "text",
            text_body="When does the garbage truck arrive?"
        )
        assert res["status"] != "awaiting_language"
    finally:
        _cleanup(db, citizen, user)


# ─────────────────────────────────────────────
# 5. START / LANG / LANGUAGE explicit commands
# ─────────────────────────────────────────────

@pytest.mark.parametrize("cmd", ["START", "start", "LANG", "LANGUAGE", "lang", "language"])
def test_explicit_commands_always_reopen_language_selection(db, sent_messages, cmd):
    """
    START, LANG, and LANGUAGE must reopen language selection even when the
    citizen already has a saved preferred_language.
    """
    citizen, user = _make_new_citizen(
        db, preferred_language="en", conversation_state="IDLE"
    )
    try:
        res = WhatsAppService.handle_incoming_message(
            db, citizen.phone_number, "text", text_body=cmd
        )
        assert res["status"] == "awaiting_language"
        assert len(sent_messages) == 1
        button_ids = [b["reply"]["id"] for b in sent_messages[0]["interactive"]["action"]["buttons"]]
        assert "LANG_EN" in button_ids
        assert "LANG_MR" in button_ids
        db.refresh(citizen)
        assert citizen.conversation_state == "AWAITING_LANGUAGE"
    finally:
        _cleanup(db, citizen, user)


# ─────────────────────────────────────────────
# 6. Gemini isolation during language gate
# ─────────────────────────────────────────────

@pytest.mark.parametrize("trigger", ["hey", "hii", "hello", "yoo", "yo", "START"])
def test_gemini_not_called_during_language_gate(db, sent_messages, trigger):
    """
    Gemini must never be invoked when the language gate intercepts a message.
    """
    citizen, user = _make_new_citizen(
        db, preferred_language=None, conversation_state="IDLE"
    )
    try:
        res = WhatsAppService.handle_incoming_message(
            db, citizen.phone_number, "text", text_body=trigger
        )
        assert res["status"] == "awaiting_language"
        assert not res.get("ai_classified")
    finally:
        _cleanup(db, citizen, user)


def test_language_button_not_sent_to_gemini(db, sent_messages):
    """
    Language selection button payloads must be handled deterministically without Gemini.
    """
    citizen, user = _make_new_citizen(
        db, preferred_language=None, conversation_state="AWAITING_LANGUAGE"
    )
    try:
        res = WhatsAppService.handle_incoming_message(
            db, citizen.phone_number, "interactive", text_body="LANG_EN"
        )
        assert res["status"] == "language_selected"
        assert not res.get("ai_classified")
    finally:
        _cleanup(db, citizen, user)


# ─────────────────────────────────────────────
# 7. Full Menu and Service Routings
# ─────────────────────────────────────────────

def test_full_menu_sends_all_eight_options(db, sent_messages):
    """
    OPEN_FULL_MENU sends a single message containing all 8 numbered options
    and the 3 primary quick action buttons.
    """
    citizen, user = _make_new_citizen(
        db, preferred_language="en", conversation_state="IDLE"
    )
    try:
        res = WhatsAppService.handle_incoming_message(
            db, citizen.phone_number, "interactive", text_body="OPEN_FULL_MENU"
        )
        assert res["status"] == "full_menu_presented"
        assert len(sent_messages) == 1
        body = sent_messages[0]["message_text"]
        for i in range(1, 9):
            assert f"{i}." in body, f"Option {i} missing from full menu body"
        button_ids = [b["reply"]["id"] for b in sent_messages[0]["interactive"]["action"]["buttons"]]
        assert "REPORT_WASTE" in button_ids
        assert "GENERAL_COMPLAINT" in button_ids
        assert "OPEN_FULL_MENU" in button_ids
    finally:
        _cleanup(db, citizen, user)


def test_report_waste_and_general_complaint_remain_functional(db, sent_messages):
    """
    REPORT_WASTE and GENERAL_COMPLAINT primary buttons route correctly to their workflow states.
    """
    citizen, user = _make_new_citizen(
        db, preferred_language="en", conversation_state="IDLE"
    )
    try:
        res = WhatsAppService.handle_incoming_message(
            db, citizen.phone_number, "interactive", text_body="REPORT_WASTE"
        )
        assert res["status"] == "awaiting_photo"
        db.refresh(citizen)
        assert citizen.conversation_state == "AWAITING_PHOTO"

        citizen.conversation_state = "IDLE"
        citizen.pending_complaint_data = None
        db.commit()

        sent_messages.clear()
        res2 = WhatsAppService.handle_incoming_message(
            db, citizen.phone_number, "interactive", text_body="GENERAL_COMPLAINT"
        )
        assert res2["status"] == "awaiting_general_complaint"
        db.refresh(citizen)
        assert citizen.conversation_state == "AWAITING_GENERAL_COMPLAINT"
    finally:
        _cleanup(db, citizen, user)


def test_digit_1_in_awaiting_language_selects_english(db, sent_messages):
    """
    When in AWAITING_LANGUAGE state, sending '1' selects English (LANG_EN).
    """
    citizen, user = _make_new_citizen(
        db, preferred_language=None, conversation_state="AWAITING_LANGUAGE"
    )
    try:
        res = WhatsAppService.handle_incoming_message(
            db, citizen.phone_number, "text", text_body="1"
        )
        assert res["status"] == "language_selected"
        assert res["language"] == "en"
        db.refresh(citizen)
        assert citizen.preferred_language == "en"
    finally:
        _cleanup(db, citizen, user)


# ─────────────────────────────────────────────
# 8. Plain-text Language Choice Edge Cases
# ─────────────────────────────────────────────

def test_first_message_english_returns_awaiting_language(db, sent_messages):
    """
    A new citizen sending plain-text "English" on their very first message
    must receive the language-selection prompt, NOT bypass to English selection.
    """
    citizen, user = _make_new_citizen(
        db, preferred_language=None, conversation_state="IDLE"
    )
    try:
        res = WhatsAppService.handle_incoming_message(
            db, citizen.phone_number, "text", text_body="English"
        )
        assert res["status"] == "awaiting_language"
        db.refresh(citizen)
        assert citizen.preferred_language is None
        assert citizen.conversation_state == "AWAITING_LANGUAGE"
        assert len(sent_messages) == 1
        interactive = sent_messages[0]["interactive"]
        button_ids = [b["reply"]["id"] for b in interactive["action"]["buttons"]]
        assert "LANG_EN" in button_ids
        assert "LANG_MR" in button_ids
    finally:
        _cleanup(db, citizen, user)


def test_first_message_marathi_returns_awaiting_language(db, sent_messages):
    """
    A new citizen sending plain-text "Marathi" on their very first message
    must receive the language-selection prompt, NOT bypass to Marathi selection.
    """
    citizen, user = _make_new_citizen(
        db, preferred_language=None, conversation_state="IDLE"
    )
    try:
        res = WhatsAppService.handle_incoming_message(
            db, citizen.phone_number, "text", text_body="Marathi"
        )
        assert res["status"] == "awaiting_language"
        db.refresh(citizen)
        assert citizen.preferred_language is None
        assert citizen.conversation_state == "AWAITING_LANGUAGE"
        assert len(sent_messages) == 1
        interactive = sent_messages[0]["interactive"]
        button_ids = [b["reply"]["id"] for b in interactive["action"]["buttons"]]
        assert "LANG_EN" in button_ids
        assert "LANG_MR" in button_ids
    finally:
        _cleanup(db, citizen, user)


def test_first_message_marathi_script_returns_awaiting_language(db, sent_messages):
    """
    A new citizen sending Devanagari script "मराठी" on their very first message
    must receive the language-selection prompt, NOT bypass to Marathi selection.
    """
    citizen, user = _make_new_citizen(
        db, preferred_language=None, conversation_state="IDLE"
    )
    try:
        res = WhatsAppService.handle_incoming_message(
            db, citizen.phone_number, "text", text_body="मराठी"
        )
        assert res["status"] == "awaiting_language"
        db.refresh(citizen)
        assert citizen.preferred_language is None
        assert citizen.conversation_state == "AWAITING_LANGUAGE"
        assert len(sent_messages) == 1
        interactive = sent_messages[0]["interactive"]
        button_ids = [b["reply"]["id"] for b in interactive["action"]["buttons"]]
        assert "LANG_EN" in button_ids
        assert "LANG_MR" in button_ids
    finally:
        _cleanup(db, citizen, user)


def test_replying_english_after_selector_selects_english(db, sent_messages):
    """
    After receiving the language selector (citizen is in AWAITING_LANGUAGE),
    replying plain-text "English" persists 'en' and sends the English welcome template.
    """
    citizen, user = _make_new_citizen(
        db, preferred_language=None, conversation_state="AWAITING_LANGUAGE"
    )
    try:
        res = WhatsAppService.handle_incoming_message(
            db, citizen.phone_number, "text", text_body="English"
        )
        assert res["status"] == "language_selected"
        assert res["language"] == "en"
        db.refresh(citizen)
        assert citizen.preferred_language == "en"
        assert citizen.conversation_state == "IDLE"
        assert len(sent_messages) == 1
        interactive = sent_messages[0]["interactive"]
        assert interactive["type"] == "button"
        button_ids = [b["reply"]["id"] for b in interactive["action"]["buttons"]]
        assert "REPORT_WASTE" in button_ids
        assert "GENERAL_COMPLAINT" in button_ids
        assert "OPEN_FULL_MENU" in button_ids
    finally:
        _cleanup(db, citizen, user)


def test_replying_marathi_after_selector_selects_marathi(db, sent_messages):
    """
    After receiving the language selector (citizen is in AWAITING_LANGUAGE),
    replying plain-text "Marathi" persists 'mr' and sends the Marathi welcome template.
    """
    citizen, user = _make_new_citizen(
        db, preferred_language=None, conversation_state="AWAITING_LANGUAGE"
    )
    try:
        res = WhatsAppService.handle_incoming_message(
            db, citizen.phone_number, "text", text_body="Marathi"
        )
        assert res["status"] == "language_selected"
        assert res["language"] == "mr"
        db.refresh(citizen)
        assert citizen.preferred_language == "mr"
        assert citizen.conversation_state == "IDLE"
        assert len(sent_messages) == 1
        interactive = sent_messages[0]["interactive"]
        assert interactive["type"] == "button"
        button_ids = [b["reply"]["id"] for b in interactive["action"]["buttons"]]
        assert "REPORT_WASTE" in button_ids
        assert "GENERAL_COMPLAINT" in button_ids
        assert "OPEN_FULL_MENU" in button_ids
    finally:
        _cleanup(db, citizen, user)
