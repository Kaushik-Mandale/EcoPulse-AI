from fastapi import APIRouter, Request, Response, Depends, Query, HTTPException, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
import hmac
import hashlib
import json
import logging
from typing import Optional

from server.database.db import get_db
from server.utils.config import config
from server.utils.security import get_current_admin_user
from server.services.whatsapp_service import WhatsAppService
from server.models.whatsapp_session import WhatsAppCitizen, WhatsAppProcessedMessage
from server.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()


def verify_meta_signature(raw_body: bytes, signature_header: Optional[str]) -> None:
    """
    Validates Meta WhatsApp Cloud API X-Hub-Signature-256 HMAC-SHA256 signature.
    """
    secret = config.META_APP_SECRET
    if not secret:
        if config.ENV.lower() == "production":
            logger.error("[META WHATSAPP] META_APP_SECRET is not configured in production.")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Signature verification unavailable in production."
            )
        # In non-production without secret configured, bypass verification
        return

    if not signature_header:
        logger.warning("[META WHATSAPP] Missing X-Hub-Signature-256 header.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing X-Hub-Signature-256 header"
        )

    if not signature_header.startswith("sha256="):
        logger.warning("[META WHATSAPP] Invalid signature prefix format.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid signature format"
        )

    received_sig = signature_header[7:]
    expected_sig = hmac.new(
        secret.encode("utf-8"),
        raw_body,
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(received_sig, expected_sig):
        logger.warning("[META WHATSAPP] Webhook signature mismatch.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid signature"
        )


# ---------------------------------------------------------
# 1. Meta WhatsApp Cloud API Webhook Handshake (GET)
# ---------------------------------------------------------
@router.get("/webhook", response_class=PlainTextResponse)
def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge")
):
    """
    Webhook verification handshake for Meta WhatsApp Business Cloud API.
    """
    if hub_mode == "subscribe" and hub_verify_token == config.WHATSAPP_VERIFY_TOKEN:
        logger.info("[META WHATSAPP] Webhook verified successfully!")
        return str(hub_challenge)
    
    logger.warning(f"[META WHATSAPP] Webhook verification failed. Token mismatch.")
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Verification token mismatch")


# ---------------------------------------------------------
# 2. Meta WhatsApp Cloud API Message Receiver (POST)
# ---------------------------------------------------------
@router.post("/webhook")
async def receive_meta_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Receives incoming WhatsApp messages from Meta Graph API.
    Verifies HMAC-SHA256 signature and guarantees message idempotency.
    """
    raw_body = await request.body()
    signature_header = request.headers.get("X-Hub-Signature-256")
    verify_meta_signature(raw_body, signature_header)

    try:
        body = json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except Exception:
        return {"status": "ignored", "reason": "invalid_json"}

    # Validate Meta event structure
    if "entry" not in body or not body["entry"]:
        return {"status": "ignored", "reason": "no_entry"}

    for entry in body.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            messages = value.get("messages", [])
            for msg in messages:
                msg_id = (msg.get("id") or "").strip()
                sender_phone = msg.get("from", "")
                msg_type = msg.get("type", "text")
                text_content = ""
                media_url = ""
                latitude = None
                longitude = None

                # Idempotency check: prevent duplicate message processing
                if msg_id:
                    existing = db.query(WhatsAppProcessedMessage).filter(
                        WhatsAppProcessedMessage.message_id == msg_id
                    ).first()
                    if existing:
                        logger.info(f"[META WHATSAPP] Duplicate message ID '{msg_id[:15]}...' ignored.")
                        continue

                    # Attempt persistent registration with unique constraint protection against race conditions
                    try:
                        processed_msg = WhatsAppProcessedMessage(
                            message_id=msg_id,
                            phone_number=sender_phone,
                            message_type=msg_type
                        )
                        db.add(processed_msg)
                        db.commit()
                    except IntegrityError:
                        db.rollback()
                        logger.info(f"[META WHATSAPP] Concurrent duplicate message ID '{msg_id[:15]}...' caught by constraint.")
                        continue
                    except Exception as e:
                        db.rollback()
                        logger.error(f"[META WHATSAPP] Error registering processed message: {e}")
                        continue

                media_id = ""
                if msg_type == "text":
                    text_content = msg.get("text", {}).get("body", "")
                elif msg_type == "interactive":
                    interactive = msg.get("interactive", {})
                    if "button_reply" in interactive:
                        text_content = interactive["button_reply"].get("id", "")
                    elif "list_reply" in interactive:
                        text_content = interactive["list_reply"].get("id", "")
                elif msg_type == "image":
                    image_obj = msg.get("image", {})
                    media_id = image_obj.get("id", "")
                    media_url = f"https://graph.facebook.com/{config.WHATSAPP_GRAPH_API_VERSION}/{media_id}" if media_id else ""
                elif msg_type == "location":
                    loc = msg.get("location", {})
                    latitude = loc.get("latitude")
                    longitude = loc.get("longitude")

                WhatsAppService.handle_incoming_message(
                    db=db,
                    sender_phone=sender_phone,
                    message_type=msg_type,
                    text_body=text_content,
                    media_url=media_url,
                    media_id=media_id,
                    latitude=latitude,
                    longitude=longitude
                )

    return {"status": "processed"}



# ---------------------------------------------------------
# 3. Twilio WhatsApp Webhook Receiver (POST)
# ---------------------------------------------------------
@router.post("/twilio-webhook")
async def receive_twilio_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Receives incoming WhatsApp messages from Twilio Sandbox / Number.
    Returns standard TwiML XML response.
    """
    form_data = await request.form()
    from_raw = form_data.get("From", "") # e.g. "whatsapp:+919876543210"
    body_text = form_data.get("Body", "")
    media_url = form_data.get("MediaUrl0", "")
    latitude = form_data.get("Latitude")
    longitude = form_data.get("Longitude")

    sender_phone = from_raw.replace("whatsapp:", "").replace("+", "").strip()
    msg_type = "image" if media_url else ("location" if latitude else "text")

    res = WhatsAppService.handle_incoming_message(
        db=db,
        sender_phone=sender_phone,
        message_type=msg_type,
        text_body=body_text,
        media_url=media_url,
        latitude=float(latitude) if latitude else None,
        longitude=float(longitude) if longitude else None
    )

    reply_text = res.get("reply", "OK")
    xml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>{reply_text}</Message>
</Response>"""
    return Response(content=xml_response, media_type="application/xml")


# ---------------------------------------------------------
# 4. Generate Household QR Code & Direct Link (POST)
# ---------------------------------------------------------
@router.post("/generate-qr")
def generate_household_qr(payload: dict):
    """
    Generates household QR payload and direct WhatsApp launch link.
    Example payload: {"ward": 12, "household_number": 1042}
    """
    ward = payload.get("ward", 12)
    house_num = payload.get("household_number", 1001)
    code = f"SHP-W{ward}-H{house_num}"
    bot_phone = config.WHATSAPP_BUSINESS_PHONE.replace("+", "").replace(" ", "")
    link = f"https://wa.me/{bot_phone}?text=JOIN%20{code}"

    return {
        "household_code": code,
        "ward": f"Ward {ward}",
        "household_number": house_num,
        "qr_scan_text": f"JOIN {code}",
        "whatsapp_direct_link": link,
        "instructions": "Print this QR code on municipal bin sticker or property tax bill."
    }


# ---------------------------------------------------------
# 5. List Authorized WhatsApp Citizens (GET)
# ---------------------------------------------------------
@router.get("/citizens")
def list_whatsapp_citizens(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """
    List registered WhatsApp citizen households in Shirpur.
    Protected: Accessible exclusively by authorized municipal administrators.
    """
    citizens = db.query(WhatsAppCitizen).order_by(WhatsAppCitizen.id.desc()).all()
    return [
        {
            "id": c.id,
            "phone_number": c.phone_number,
            "full_name": c.full_name,
            "ward": c.ward,
            "household_id": c.household_id,
            "is_authorized": c.is_authorized,
            "eco_coins": c.eco_coins,
            "preferred_language": c.preferred_language,
            "conversation_state": c.conversation_state,
            "created_at": c.created_at.isoformat() if c.created_at else None
        }
        for c in citizens
    ]


# ---------------------------------------------------------
# 6. Simulator / Developer Test Endpoint (POST)
# ---------------------------------------------------------
@router.post("/simulate-incoming")
def simulate_whatsapp_incoming(payload: dict, db: Session = Depends(get_db)):
    """
    Simulate a WhatsApp message without needing a live Meta account.
    Disabled in production environments.
    Example:
    {"phone": "919876543210", "message": "JOIN SHP-W12-H1042", "type": "text"}
    """
    if config.ENV.lower() == "production":
        logger.warning("[META WHATSAPP] Blocked access to simulator endpoint in production.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Simulator endpoint is disabled in production."
        )

    phone = payload.get("phone", "919876543210")
    message = payload.get("message", "1")
    msg_type = payload.get("type", "text")
    media_url = payload.get("media_url", "")
    media_id = payload.get("media_id", "")
    lat = payload.get("latitude")
    lng = payload.get("longitude")

    res = WhatsAppService.handle_incoming_message(
        db=db,
        sender_phone=phone,
        message_type=msg_type,
        text_body=message,
        media_url=media_url,
        media_id=media_id,
        latitude=lat,
        longitude=lng
    )
    return res
