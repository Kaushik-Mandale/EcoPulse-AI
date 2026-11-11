import json
import uuid
import pytest
from server.database.db import SessionLocal
from server.models.whatsapp_session import WhatsAppCitizen
from server.models.user import User
from server.services.whatsapp_service import WhatsAppService


@pytest.fixture
def db():
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
        assert len(rows) == 9  # exactly 9 options

        expected_ids = {
            "MENU_REPORT_WASTE",
            "MENU_GENERAL_COMPLAINT",
            "MENU_VEHICLE_TRACKING",
            "MENU_COLLECTION_SCHEDULE",
            "MENU_ECO_WALLET",
            "MENU_MY_COMPLAINTS",
            "MENU_LEADERBOARD",
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
    """Test dispatching each of the 9 interactive list options."""
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

    # 7. Leaderboard
    res7 = WhatsAppService.handle_incoming_message(
        db, auth_citizen.phone_number, "interactive", text_body="MENU_LEADERBOARD"
    )
    assert res7["status"] == "leaderboard_unavailable"

    # 8. Notices
    res8 = WhatsAppService.handle_incoming_message(
        db, auth_citizen.phone_number, "interactive", text_body="MENU_NOTICES"
    )
    assert res8["status"] == "notices_unavailable"

    # 9. Help
    res9 = WhatsAppService.handle_incoming_message(
        db, auth_citizen.phone_number, "interactive", text_body="MENU_HELP_LANG"
    )
    assert res9["status"] == "help"


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


def test_invalid_selection_handled(db, auth_citizen):
    """Test that invalid selections provide helpful feedback and present the menu."""
    res = WhatsAppService.handle_incoming_message(
        db, auth_citizen.phone_number, "text", text_body="UNKNOWN_OPTION_XYZ"
    )
    assert res["status"] == "menu_presented"
    assert "Unrecognized option" in res["reply"] or "पर्याय उपलब्ध नाही" in res["reply"]


def test_numeric_compatibility_preserved(db, auth_citizen):
    """Test that numeric 1 to 9 inputs remain 100% functional."""
    # Option 1
    res1 = WhatsAppService.handle_incoming_message(
        db, auth_citizen.phone_number, "text", text_body="1"
    )
    assert res1["status"] == "awaiting_photo"
    auth_citizen.conversation_state = "IDLE"
    db.commit()

    # Option 5
    res5 = WhatsAppService.handle_incoming_message(
        db, auth_citizen.phone_number, "text", text_body="5"
    )
    assert res5["status"] == "wallet_info"


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

