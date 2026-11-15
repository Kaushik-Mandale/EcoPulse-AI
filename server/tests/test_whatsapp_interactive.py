import json
import uuid
import pytest
from server.database.db import SessionLocal
from server.models.whatsapp_session import WhatsAppCitizen
from server.models.user import User
from server.services.whatsapp_service import WhatsAppService


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
    """Create a linked/authorized citizen for WhatsApp testing with cleanup."""
    suffix = uuid.uuid4().hex[:8]
    test_phone = f"9198{uuid.uuid4().int % 100000000:08d}"
    user = User(
        full_name="Priya Patil",
        email=f"priya_{suffix}@cityswap.io",
        phone=test_phone,
        role="citizen",
        is_active=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    citizen = WhatsAppCitizen(
        phone_number=test_phone,
        full_name="Priya Patil",
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

    # Cleanup
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


def test_build_main_menu_interactive_spec_compliance():
    """Verify that interactive list message complies strictly with Meta Cloud API specifications."""
    for lang in ["en", "mr"]:
        payload = WhatsAppService.build_main_menu_interactive(lang=lang, greeting_text="Hello Citizen")
        assert payload["type"] == "list"
        assert len(payload["header"]["text"]) <= 60
        assert len(payload["body"]["text"]) <= 1024
        assert len(payload["footer"]["text"]) <= 60

        action = payload["action"]
        assert len(action["button"]) <= 20

        sections = action["sections"]
        assert len(sections) == 1
        assert len(sections[0]["title"]) <= 24

        rows = sections[0]["rows"]
        assert len(rows) == 8  # exactly 8 options (Leaderboard removed)

        expected_ids = {
            "MENU_REPORT_WASTE",
            "MENU_GENERAL_COMPLAINT",
            "MENU_VEHICLE_TRACKING",
            "MENU_COLLECTION_SCHEDULE",
            "MENU_ECO_WALLET",
            "MENU_MY_COMPLAINTS",
            "MENU_NOTICES",
            "MENU_HELP_LANG"
        }
        row_ids = {r["id"] for r in rows}
        assert row_ids == expected_ids

        for r in rows:
            assert len(r["id"]) <= 200
            assert len(r["title"]) <= 24
            assert len(r["description"]) <= 72


def test_build_quick_buttons_interactive():
    """Verify button payload follows Meta constraints (max 3 buttons, title <= 20 chars)."""
    buttons = [
        ("BTN_1", "Option One"),
        ("BTN_2", "Option Two"),
        ("BTN_3", "Option Three"),
        ("BTN_4", "Should be ignored")
    ]
    interactive = WhatsAppService.build_quick_buttons_interactive(
        body_text="Choose one",
        buttons=buttons,
        header_text="Header",
        footer_text="Footer"
    )
    assert interactive["type"] == "button"
    assert interactive["body"]["text"] == "Choose one"
    assert len(interactive["action"]["buttons"]) == 3
    for btn in interactive["action"]["buttons"]:
        assert btn["type"] == "reply"
        assert len(btn["reply"]["title"]) <= 20
        assert len(btn["reply"]["id"]) <= 256


def test_interactive_list_selections(db, auth_citizen):
    """Test dispatching each of the 8 interactive list options and verifying Leaderboard removal."""
    # 1. Report waste
    res1 = WhatsAppService.handle_incoming_message(
        db, auth_citizen.phone_number, "interactive", text_body="MENU_REPORT_WASTE"
    )
    assert res1["status"] == "awaiting_photo"
    auth_citizen.conversation_state = "IDLE"
    db.commit()

    # 2. General complaint
    res2 = WhatsAppService.handle_incoming_message(
        db, auth_citizen.phone_number, "interactive", text_body="MENU_GENERAL_COMPLAINT"
    )
    assert res2["status"] == "awaiting_general_complaint"
    auth_citizen.conversation_state = "IDLE"
    db.commit()

    # 3. Vehicle tracking
    res3 = WhatsAppService.handle_incoming_message(
        db, auth_citizen.phone_number, "interactive", text_body="MENU_VEHICLE_TRACKING"
    )
    assert res3["status"] == "truck_unavailable"

    # 4. Collection schedule
    res4 = WhatsAppService.handle_incoming_message(
        db, auth_citizen.phone_number, "interactive", text_body="MENU_COLLECTION_SCHEDULE"
    )
    assert res4["status"] == "schedule_unavailable"

    # 5. Eco Wallet
    res5 = WhatsAppService.handle_incoming_message(
        db, auth_citizen.phone_number, "interactive", text_body="MENU_ECO_WALLET"
    )
    assert res5["status"] == "wallet_info"

    # 6. My Complaints
    res6 = WhatsAppService.handle_incoming_message(
        db, auth_citizen.phone_number, "interactive", text_body="MENU_MY_COMPLAINTS"
    )
    assert res6["status"] == "track_complaints"

    # 7. Notices (renumbered option 7)
    res7 = WhatsAppService.handle_incoming_message(
        db, auth_citizen.phone_number, "interactive", text_body="MENU_NOTICES"
    )
    assert res7["status"] == "notices_unavailable"

    # 8. Help & Language (renumbered option 8)
    res8 = WhatsAppService.handle_incoming_message(
        db, auth_citizen.phone_number, "interactive", text_body="MENU_HELP_LANG"
    )
    assert res8["status"] == "help"

    # Removed Leaderboard Option completely: MENU_LEADERBOARD is now unrecognized and presents menu
    res_lb = WhatsAppService.handle_incoming_message(
        db, auth_citizen.phone_number, "interactive", text_body="MENU_LEADERBOARD"
    )
    assert res_lb["status"] == "menu_presented"


def test_interactive_language_buttons(db, auth_citizen):
    """Test switching languages via interactive buttons."""
    # Switch to Marathi
    res_mr = WhatsAppService.handle_incoming_message(
        db, auth_citizen.phone_number, "interactive", text_body="LANG_MR"
    )
    assert res_mr["status"] == "help"
    db.refresh(auth_citizen)
    assert auth_citizen.preferred_language == "mr"

    # Switch to English
    res_en = WhatsAppService.handle_incoming_message(
        db, auth_citizen.phone_number, "interactive", text_body="LANG_EN"
    )
    assert res_en["status"] == "help"
    db.refresh(auth_citizen)
    assert auth_citizen.preferred_language == "en"


def test_interactive_back_to_menu(db, auth_citizen):
    """Test Main Menu button returns to main menu."""
    res = WhatsAppService.handle_incoming_message(
        db, auth_citizen.phone_number, "interactive", text_body="MENU_MAIN"
    )
    assert res["status"] == "menu_presented"


@pytest.mark.parametrize("greeting", ["HI", "HELLO", "MENU"])
def test_greeting_sends_chat_menu_and_quick_actions(db, auth_citizen, sent_messages, greeting):
    """Greetings send the bilingual text menu in chat and a separate compliant shortcut message."""
    res = WhatsAppService.handle_incoming_message(
        db, auth_citizen.phone_number, "text", text_body=greeting
    )

    assert res["status"] == "menu_presented"
    assert len(sent_messages) == 2
    text_menu = sent_messages[0]["message_text"]
    assert sent_messages[0]["interactive"] is None
    assert "नमस्कार! Hello!" in text_menu
    assert "EcoPulse AI" in text_menu
    assert "Reply with a number (1-8) or keyword" in text_menu
    for label in (
        "Report Waste", "General Complaint", "Garbage Vehicle Tracking",
        "Collection Schedule", "EcoWallet & Rewards", "My Complaints",
        "Municipal Notices", "Help & Change Language",
    ):
        assert label in text_menu
    assert "Leaderboard" not in text_menu

    shortcut_message = sent_messages[1]
    interactive = shortcut_message["interactive"]
    assert interactive["type"] == "button"
    assert len(interactive["action"]["buttons"]) == 3
    assert [button["reply"]["id"] for button in interactive["action"]["buttons"]] == [
        "MENU_REPORT_WASTE",
        "MENU_GENERAL_COMPLAINT",
        "MENU_FULL_MENU",
    ]


def test_full_menu_button_opens_existing_interactive_list(db, auth_citizen, sent_messages):
    result = WhatsAppService.handle_incoming_message(
        db, auth_citizen.phone_number, "interactive", text_body="MENU_FULL_MENU"
    )

    assert result["status"] == "full_menu_presented"
    assert len(sent_messages) == 1
    interactive = sent_messages[0]["interactive"]
    assert interactive["type"] == "list"
    assert len(interactive["action"]["sections"][0]["rows"]) == 8


def test_invalid_selection_handled(db, auth_citizen):
    """Test that invalid selections provide helpful feedback and present the menu."""
    res = WhatsAppService.handle_incoming_message(
        db, auth_citizen.phone_number, "text", text_body="UNKNOWN_OPTION_XYZ"
    )
    assert res["status"] == "menu_presented"
    assert "Unrecognized option" in res["reply"] or "पर्याय उपलब्ध नाही" in res["reply"]


def test_numeric_compatibility_preserved(db, auth_citizen, sent_messages):
    """All numeric choices (1-8) continue dispatching to their handlers, option 7 is notices, 8 is help."""
    expected_statuses = [
        "awaiting_photo",
        "awaiting_general_complaint",
        "truck_unavailable",
        "schedule_unavailable",
        "wallet_info",
        "track_complaints",
        "notices_unavailable",
        "help",
    ]

    for number, expected_status in enumerate(expected_statuses, start=1):
        result = WhatsAppService.handle_incoming_message(
            db, auth_citizen.phone_number, "text", text_body=str(number)
        )
        assert result["status"] == expected_status
        auth_citizen.conversation_state = "IDLE"
        db.commit()

    # Legacy option 9 maps to help
    res9 = WhatsAppService.handle_incoming_message(
        db, auth_citizen.phone_number, "text", text_body="9"
    )
    assert res9["status"] == "help"


@pytest.mark.parametrize(
    ("keyword", "expected_status"),
    [
        ("report", "awaiting_photo"),
        ("तक्रार नोंद", "awaiting_photo"),
        ("general", "awaiting_general_complaint"),
        ("सामान्य", "awaiting_general_complaint"),
        ("vehicle", "truck_unavailable"),
        ("घंटागाडी", "truck_unavailable"),
        ("schedule", "schedule_unavailable"),
        ("वेळापत्रक", "schedule_unavailable"),
        ("wallet", "wallet_info"),
        ("वॉलेट", "wallet_info"),
        ("my complaints", "track_complaints"),
        ("माझ्या तक्रारी", "track_complaints"),
        ("notices", "notices_unavailable"),
        ("सूचना", "notices_unavailable"),
        ("help", "help"),
        ("मदत", "help"),
    ],
)
def test_english_and_marathi_keywords_route_existing_handlers(
    db, auth_citizen, sent_messages, keyword, expected_status
):
    result = WhatsAppService.handle_incoming_message(
        db, auth_citizen.phone_number, "text", text_body=keyword
    )

    assert result["status"] == expected_status


def test_webhook_interactive_list_and_button_parsing(auth_citizen, monkeypatch):
    """Test full webhook route parsing for interactive list and button replies with valid HMAC signature."""
    import hmac
    import hashlib
    from fastapi.testclient import TestClient
    from server.main import app
    from server.utils.config import config

    test_secret = "test_meta_app_secret_321"
    monkeypatch.setattr(config, "META_APP_SECRET", test_secret)

    client = TestClient(app)

    # 1. Interactive list reply payload
    msg_id = f"wamid.interactive_list_{uuid.uuid4().hex[:6]}"
    list_payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "id": msg_id,
                                    "from": auth_citizen.phone_number,
                                    "type": "interactive",
                                    "interactive": {
                                        "type": "list_reply",
                                        "list_reply": {
                                            "id": "MENU_REPORT_WASTE",
                                            "title": "Report Waste"
                                        }
                                    }
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }
    raw_body = json.dumps(list_payload).encode("utf-8")
    sig = hmac.new(test_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    res = client.post(
        "/api/whatsapp/webhook",
        content=raw_body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": f"sha256={sig}"}
    )
    assert res.status_code == 200

    # 2. Interactive button reply payload
    btn_msg_id = f"wamid.interactive_btn_{uuid.uuid4().hex[:6]}"
    btn_payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "id": btn_msg_id,
                                    "from": auth_citizen.phone_number,
                                    "type": "interactive",
                                    "interactive": {
                                        "type": "button_reply",
                                        "button_reply": {
                                            "id": "MENU_MAIN",
                                            "title": "Main Menu"
                                        }
                                    }
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }
    raw_btn = json.dumps(btn_payload).encode("utf-8")
    btn_sig = hmac.new(test_secret.encode("utf-8"), raw_btn, hashlib.sha256).hexdigest()

    res_btn = client.post(
        "/api/whatsapp/webhook",
        content=raw_btn,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": f"sha256={btn_sig}"}
    )
    assert res_btn.status_code == 200


def test_verify_and_link_commands_not_intercepted(db, auth_citizen):
    """Ensure VERIFY <code> and LINK <code> are never intercepted or broken by interactive routing."""
    # VERIFY with unverified or non-existent code returns verification failure, not menu
    verify_res = WhatsAppService.handle_incoming_message(
        db, auth_citizen.phone_number, "text", text_body="VERIFY 999999"
    )
    assert verify_res["status"] in ("no_challenge", "invalid_or_expired", "invalid_format", "not_found")
    assert verify_res.get("verified") is False

    # LINK with invalid code returns link_failed, not menu
    link_res = WhatsAppService.handle_incoming_message(
        db, auth_citizen.phone_number, "text", text_body="LINK NONEXISTENT999"
    )
    assert link_res["status"] == "link_failed"


def test_complaint_creation_regression(db, auth_citizen):
    """Ensure photo + location reporting flow remains intact and assigns task."""
    # Step 1: Send Photo
    photo_res = WhatsAppService.handle_incoming_message(
        db,
        auth_citizen.phone_number,
        "image",
        media_url="https://lookaside.fbsbx.com/test_image.jpg"
    )
    assert photo_res["status"] == "awaiting_location"

    # Step 2: Send Geotagged Location Pin
    loc_res = WhatsAppService.handle_incoming_message(
        db,
        auth_citizen.phone_number,
        "location",
        latitude=20.9042,
        longitude=74.7749
    )
    assert loc_res["status"] == "complaint_created"
    assert loc_res["ticket"].startswith("DHL-2026-")
    assert "Ticket ID" in loc_res["reply"] or "तक्रार क्र" in loc_res["reply"]


def test_location_request_payload_format():
    """Verify native location request message structure adheres to Meta specifications."""
    prompt = "📍 कृपया कचरा असलेल्या ठिकाणाचे लोकेशन शेअर करा / Please share the waste location."
    payload = WhatsAppService.build_location_request_interactive(prompt)
    assert payload["type"] == "location_request_message"
    assert payload["body"]["text"] == prompt
    assert len(payload["body"]["text"]) <= 1024
    assert payload["action"] == {"name": "send_location"}


def test_photo_submission_triggers_photo_ack_and_location_request(db, auth_citizen, sent_messages):
    """Submitting a photo sends photo acknowledgment and native location request interactive message."""
    res = WhatsAppService.handle_incoming_message(
        db,
        auth_citizen.phone_number,
        "image",
        media_url="https://lookaside.fbsbx.com/sample_waste_photo.jpg"
    )

    assert res["status"] == "awaiting_location"
    db.refresh(auth_citizen)
    assert auth_citizen.conversation_state == "AWAITING_LOCATION"

    # Verifies both outbound messages: ack text message and native location request
    assert len(sent_messages) == 2
    ack_msg = sent_messages[0]
    assert "Photo received" in ack_msg["message_text"] or "फोटो प्राप्त झाला" in ack_msg["message_text"]

    loc_msg = sent_messages[1]
    assert loc_msg["interactive"] is not None
    assert loc_msg["interactive"]["type"] == "location_request_message"
    assert loc_msg["interactive"]["action"]["name"] == "send_location"


def test_manual_address_fallback_for_waste_complaint(db, auth_citizen):
    """Test manual text address fallback for citizens whose devices do not share location pins."""
    # Step 1: Send Photo
    WhatsAppService.handle_incoming_message(
        db,
        auth_citizen.phone_number,
        "image",
        media_url="https://lookaside.fbsbx.com/manual_waste.jpg"
    )

    # Step 2: Send Address in English format
    addr_res = WhatsAppService.handle_incoming_message(
        db,
        auth_citizen.phone_number,
        "text",
        text_body="ADDRESS: 14 Agra Road, Near Municipal Corporation, Dhule"
    )

    assert addr_res["status"] == "complaint_created"
    assert addr_res["ticket"].startswith("DHL-2026-")
    db.refresh(auth_citizen)
    assert auth_citizen.conversation_state == "IDLE"

    # Verify complaint record in database has the provided address
    from server.models.complaint import Complaint
    c = db.query(Complaint).filter(Complaint.tracking_number == addr_res["ticket"]).first()
    assert c is not None
    assert "14 Agra Road" in c.location_address

    # Step 3: Test Marathi prefix fallback
    WhatsAppService.handle_incoming_message(
        db,
        auth_citizen.phone_number,
        "image",
        media_url="https://lookaside.fbsbx.com/manual_waste2.jpg"
    )
    addr_mr_res = WhatsAppService.handle_incoming_message(
        db,
        auth_citizen.phone_number,
        "text",
        text_body="पत्ता: देवपूर, धुळे 424002"
    )
    assert addr_mr_res["status"] == "complaint_created"
    c2 = db.query(Complaint).filter(Complaint.tracking_number == addr_mr_res["ticket"]).first()
    assert c2 is not None
    assert "देवपूर, धुळे 424002" in c2.location_address


def test_event_reporting_full_flow_success(db, auth_citizen, sent_messages):
    """Complete 5-step public event reporting workflow through confirmation and persistence."""
    from server.models.event_report import EventReport

    # Step 1: Initiate event reporting
    init_res = WhatsAppService.handle_incoming_message(
        db, auth_citizen.phone_number, "text", text_body="event"
    )
    assert init_res["status"] == "awaiting_event_category"
    db.refresh(auth_citizen)
    assert auth_citizen.conversation_state == "AWAITING_EVENT_CATEGORY"

    # Step 2: Choose category (e.g. RELIGIOUS / Religious Event)
    cat_res = WhatsAppService.handle_incoming_message(
        db, auth_citizen.phone_number, "interactive", text_body="RELIGIOUS"
    )
    assert cat_res["status"] == "awaiting_event_date"
    db.refresh(auth_citizen)
    assert auth_citizen.conversation_state == "AWAITING_EVENT_DATE"

    # Step 3: Provide event date
    date_res = WhatsAppService.handle_incoming_message(
        db, auth_citizen.phone_number, "text", text_body="28/11/2026"
    )
    assert date_res["status"] == "awaiting_event_time"
    db.refresh(auth_citizen)
    assert auth_citizen.conversation_state == "AWAITING_EVENT_TIME"

    # Step 4: Provide event time
    time_res = WhatsAppService.handle_incoming_message(
        db, auth_citizen.phone_number, "text", text_body="06:30 PM"
    )
    assert time_res["status"] == "awaiting_event_location"
    db.refresh(auth_citizen)
    assert auth_citizen.conversation_state == "AWAITING_EVENT_LOCATION"

    # Step 5: Send location pin
    loc_res = WhatsAppService.handle_incoming_message(
        db,
        auth_citizen.phone_number,
        "location",
        latitude=20.9042,
        longitude=74.7749
    )
    assert loc_res["status"] == "awaiting_event_confirmation"
    db.refresh(auth_citizen)
    assert auth_citizen.conversation_state == "AWAITING_EVENT_CONFIRMATION"
    assert "28/11/2026" in loc_res["reply"]
    assert "06:30 PM" in loc_res["reply"]

    # Step 6: Confirm event submission
    confirm_res = WhatsAppService.handle_incoming_message(
        db, auth_citizen.phone_number, "interactive", text_body="EVENT_CONFIRM"
    )
    assert confirm_res["status"] == "event_created"
    assert confirm_res["reference_id"].startswith("EVT-2026-")
    db.refresh(auth_citizen)
    assert auth_citizen.conversation_state == "IDLE"
    assert auth_citizen.pending_complaint_data is None

    # Verify event report persistence in database
    from datetime import date
    saved_event = db.query(EventReport).filter(
        EventReport.reference_id == confirm_res["reference_id"]
    ).first()
    assert saved_event is not None
    assert "Religious" in saved_event.category or "धार्मिक" in saved_event.category
    assert saved_event.event_date == date(2026, 11, 28)
    assert saved_event.event_time == "06:30 PM"
    assert abs(saved_event.latitude - 20.9042) < 0.001
    assert abs(saved_event.longitude - 74.7749) < 0.001
    assert saved_event.whatsapp_citizen_id == auth_citizen.id


def test_event_reporting_manual_address_fallback(db, auth_citizen):
    """Event reporting supports manual address input as fallback when location pin unavailable."""
    from server.models.event_report import EventReport

    # Fast forward citizen to AWAITING_EVENT_LOCATION
    auth_citizen.conversation_state = "AWAITING_EVENT_LOCATION"
    auth_citizen.pending_complaint_data = json.dumps({
        "event_category": "PUBLIC",
        "event_date": "20/12/2026",
        "event_time": "10:00 AM"
    })
    db.commit()

    # Provide venue address
    loc_res = WhatsAppService.handle_incoming_message(
        db,
        auth_citizen.phone_number,
        "text",
        text_body="ADDRESS: SSVPS Ground, Vidyanagari, Deopur, Dhule"
    )
    assert loc_res["status"] == "awaiting_event_confirmation"
    assert "SSVPS Ground" in loc_res["reply"]

    # Confirm
    conf_res = WhatsAppService.handle_incoming_message(
        db, auth_citizen.phone_number, "text", text_body="CONFIRM"
    )
    assert conf_res["status"] == "event_created"

    saved = db.query(EventReport).filter(EventReport.reference_id == conf_res["reference_id"]).first()
    assert saved is not None
    assert "SSVPS Ground" in saved.location_address


def test_event_reporting_date_validation(db, auth_citizen):
    """Test date validation rejects past dates, invalid formats, and nonsensical dates."""
    auth_citizen.conversation_state = "AWAITING_EVENT_DATE"
    auth_citizen.pending_complaint_data = json.dumps({"event_category": "WEDDING"})
    db.commit()

    # Past date
    res_past = WhatsAppService.handle_incoming_message(
        db, auth_citizen.phone_number, "text", text_body="01/01/2020"
    )
    assert res_past["status"] == "invalid_event_date"
    db.refresh(auth_citizen)
    assert auth_citizen.conversation_state == "AWAITING_EVENT_DATE"

    # Wrong format (YYYY-MM-DD instead of DD/MM/YYYY)
    res_fmt = WhatsAppService.handle_incoming_message(
        db, auth_citizen.phone_number, "text", text_body="2026-12-25"
    )
    assert res_fmt["status"] == "invalid_event_date"

    # Non-existent date
    res_bad = WhatsAppService.handle_incoming_message(
        db, auth_citizen.phone_number, "text", text_body="31/02/2026"
    )
    assert res_bad["status"] == "invalid_event_date"

    # Valid future date transitions to next state
    res_ok = WhatsAppService.handle_incoming_message(
        db, auth_citizen.phone_number, "text", text_body="15/12/2026"
    )
    assert res_ok["status"] == "awaiting_event_time"
    db.refresh(auth_citizen)
    assert auth_citizen.conversation_state == "AWAITING_EVENT_TIME"


def test_event_reporting_time_validation(db, auth_citizen):
    """Test time validation supports both 12-hour (AM/PM) and 24-hour formats and formats canonically."""
    auth_citizen.conversation_state = "AWAITING_EVENT_TIME"
    auth_citizen.pending_complaint_data = json.dumps({
        "event_category": "CLEANUP",
        "event_date": "10/12/2026"
    })
    db.commit()

    # Invalid time string
    res_bad = WhatsAppService.handle_incoming_message(
        db, auth_citizen.phone_number, "text", text_body="evening at sunset"
    )
    assert res_bad["status"] == "invalid_event_time"

    # Valid 24-hour time 18:30 -> canonical 06:30 PM
    res_24 = WhatsAppService.handle_incoming_message(
        db, auth_citizen.phone_number, "text", text_body="18:30"
    )
    assert res_24["status"] == "awaiting_event_location"
    db.refresh(auth_citizen)
    data = json.loads(auth_citizen.pending_complaint_data)
    assert data["event_time"] == "06:30 PM"


def test_event_reporting_cancellation(db, auth_citizen):
    """Citizens can cancel event reporting at any point and return to clean IDLE state."""
    auth_citizen.conversation_state = "AWAITING_EVENT_TIME"
    auth_citizen.pending_complaint_data = json.dumps({
        "event_category": "FESTIVAL",
        "event_date": "15/12/2026"
    })
    db.commit()

    # Cancel via CANCEL
    res = WhatsAppService.handle_incoming_message(
        db, auth_citizen.phone_number, "text", text_body="CANCEL"
    )
    assert res["status"] in ("cancelled", "event_cancelled")
    db.refresh(auth_citizen)
    assert auth_citizen.conversation_state == "IDLE"
    assert auth_citizen.pending_complaint_data is None


def test_cross_state_isolation_event_vs_waste(db, auth_citizen):
    """Ensure strict isolation between waste complaints and event reporting."""
    # When in AWAITING_EVENT_DATE, sending a location pin is NOT processed as waste complaint
    auth_citizen.conversation_state = "AWAITING_EVENT_DATE"
    auth_citizen.pending_complaint_data = json.dumps({"event_category": "OTHER"})
    db.commit()

    loc_res = WhatsAppService.handle_incoming_message(
        db,
        auth_citizen.phone_number,
        "location",
        latitude=20.9042,
        longitude=74.7749
    )
    # The event date validator rejects the unexpected location pin and preserves event date state
    assert loc_res["status"] == "invalid_event_date"
    db.refresh(auth_citizen)
    assert auth_citizen.conversation_state == "AWAITING_EVENT_DATE"

    # When in IDLE, sending a location pin without an image asks for photo
    auth_citizen.conversation_state = "IDLE"
    auth_citizen.pending_complaint_data = None
    db.commit()

    idle_loc = WhatsAppService.handle_incoming_message(
        db,
        auth_citizen.phone_number,
        "location",
        latitude=20.9042,
        longitude=74.7749
    )
    assert idle_loc["status"] == "awaiting_photo"
    db.refresh(auth_citizen)
    assert auth_citizen.conversation_state == "AWAITING_PHOTO"


def test_conversation_recovery_after_restart(db, auth_citizen):
    """Conversation state and pending data survive application restarts and multi-turn persistence."""
    auth_citizen.conversation_state = "AWAITING_EVENT_TIME"
    auth_citizen.pending_complaint_data = json.dumps({
        "event_category": "SCHOOL",
        "event_date": "20/12/2026"
    })
    db.commit()

    # Simulate restart by refreshing from clean session
    db.expire_all()

    step_res = WhatsAppService.handle_incoming_message(
        db,
        auth_citizen.phone_number,
        "text",
        text_body="11:00 AM"
    )
    assert step_res["status"] == "awaiting_event_location"
    db.refresh(auth_citizen)
    assert auth_citizen.conversation_state == "AWAITING_EVENT_LOCATION"
    data = json.loads(auth_citizen.pending_complaint_data)
    assert data["event_category"] == "SCHOOL"
    assert data["event_date"] == "20/12/2026"
    assert data["event_time"] == "11:00 AM"
