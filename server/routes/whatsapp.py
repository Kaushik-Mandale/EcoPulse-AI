from fastapi import APIRouter, Request, Response, Depends, Query, HTTPException, status
from fastapi.responses import PlainTextResponse
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func
import hmac
import hashlib
import base64
import json
import ipaddress
import logging
import re
from typing import Optional
from urllib.parse import urlsplit

from server.database.db import get_db
from server.utils.config import config, normalize_environment
from server.utils.security import get_current_admin_user, get_current_user
from server.services.whatsapp_service import WhatsAppService
from server.services.whatsapp_link_service import WhatsAppLinkService
from server.schemas.whatsapp_link import GenerateLinkCodeResponse, LinkStatusResponse, UnlinkResponse
from server.models.whatsapp_session import WhatsAppCitizen, WhatsAppProcessedMessage
from server.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()


def verify_meta_signature(raw_body: bytes, signature_header: Optional[str]) -> None:
    """
    Validates Meta WhatsApp Cloud API X-Hub-Signature-256 HMAC-SHA256 signature.
    Fails closed if META_APP_SECRET is not configured.
    """
    secret = (config.META_APP_SECRET or "").strip()
    if not secret:
        logger.error("[META WHATSAPP] META_APP_SECRET is not configured.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Webhook signature verification is unavailable due to missing server configuration."
        )

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

                # Idempotency and atomic message-claim engine
                if msg_id:
                    existing = db.query(WhatsAppProcessedMessage).filter(
                        WhatsAppProcessedMessage.message_id == msg_id
                    ).first()

                    if existing:
                        # 1. Already completed: ignore duplicate cleanly
                        if existing.status == "COMPLETED" or not existing.status:
                            logger.info("[META WHATSAPP] Completed duplicate delivery ignored.")
                            continue

                        # 2. In-flight processing: skip duplicate delivery to prevent double-processing
                        elif existing.status == "PROCESSING":
                            logger.info("[META WHATSAPP] Concurrent duplicate delivery skipped.")
                            continue

                        # 3. Previous attempt failed: allow retry, claiming atomically
                        elif existing.status == "FAILED":
                            claimed = db.query(WhatsAppProcessedMessage).filter(
                                WhatsAppProcessedMessage.message_id == msg_id,
                                WhatsAppProcessedMessage.status == "FAILED"
                            ).update({
                                "status": "PROCESSING",
                                "error_message": None,
                                "updated_at": func.now()
                            })
                            db.commit()
                            if not claimed:
                                logger.info("[META WHATSAPP] Concurrent retry was claimed by another worker.")
                                continue
                    else:
                        # 4. New message: attempt persistent claim with status='PROCESSING'
                        try:
                            processed_msg = WhatsAppProcessedMessage(
                                message_id=msg_id,
                                phone_number=sender_phone,
                                message_type=msg_type,
                                status="PROCESSING"
                            )
                            db.add(processed_msg)
                            db.commit()
                        except IntegrityError:
                            db.rollback()
                            logger.info("[META WHATSAPP] Concurrent duplicate delivery rejected by message uniqueness.")
                            continue
                        except Exception as e:
                            db.rollback()
                            logger.error(
                                "[META WHATSAPP] Processed-message registration failed (%s).",
                                type(e).__name__,
                            )
                            raise HTTPException(
                                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                detail="Database error registering message ID"
                            )

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

                try:
                    await run_in_threadpool(
                        WhatsAppService.handle_incoming_message,
                        db=db,
                        sender_phone=sender_phone,
                        message_type=msg_type,
                        text_body=text_content,
                        media_url=media_url,
                        media_id=media_id,
                        latitude=latitude,
                        longitude=longitude,
                        message_id=msg_id
                    )

                    # Mark as COMPLETED upon successful processing
                    if msg_id:
                        db.query(WhatsAppProcessedMessage).filter(
                            WhatsAppProcessedMessage.message_id == msg_id
                        ).update({
                            "status": "COMPLETED",
                            "error_message": None,
                            "updated_at": func.now()
                        })
                        db.commit()

                except Exception as exc:
                    db.rollback()
                    safe_db_error = getattr(exc, "orig", str(exc))
                    logger.error(
                        "[META WHATSAPP] Message processing failed (%s: %s).",
                        type(exc).__name__,
                        safe_db_error,
                        exc_info=True,
                    )
                    if msg_id:
                        try:
                            db.query(WhatsAppProcessedMessage).filter(
                                WhatsAppProcessedMessage.message_id == msg_id
                            ).update({
                                "status": "FAILED",
                                "error_message": type(exc).__name__[:100],
                                "updated_at": func.now()
                            })
                            db.commit()
                        except Exception as update_err:
                            db.rollback()
                            logger.error(
                                "[META WHATSAPP] Failed to record retryable message state (%s).",
                                type(update_err).__name__,
                            )

                    if isinstance(exc, HTTPException):
                        raise exc
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Webhook message processing failed"
                    )

    return {"status": "processed"}



def verify_twilio_signature(url: str, params: dict, signature_header: Optional[str]) -> None:
    """
    Validates Twilio WhatsApp Webhook X-Twilio-Signature HMAC-SHA1 signature.
    """
    auth_token = (config.TWILIO_AUTH_TOKEN or "").strip()
    if not auth_token:
        if config.WHATSAPP_PROVIDER.lower() != "twilio":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Twilio webhook provider is disabled."
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Twilio signature verification is unavailable due to missing server configuration."
        )

    url = (url or "").strip()
    try:
        parsed_url = urlsplit(url)
        hostname = parsed_url.hostname or ""
        try:
            address = ipaddress.ip_address(hostname)
            valid_hostname = address.is_global and not getattr(
                address, "scope_id", None
            )
        except ValueError:
            ascii_hostname = hostname.encode("idna").decode("ascii").lower()
            if ascii_hostname.endswith("."):
                ascii_hostname = ascii_hostname[:-1]
            labels = ascii_hostname.split(".")
            valid_hostname = (
                len(labels) >= 2
                and len(ascii_hostname) <= 253
                and all(
                    len(label) <= 63
                    and re.fullmatch(
                        r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", label
                    )
                    for label in labels
                )
            )
        valid_url = (
            parsed_url.scheme == "https"
            and valid_hostname
            and parsed_url.username is None
            and parsed_url.password is None
            and not parsed_url.fragment
            and "#" not in url
            and "\\" not in parsed_url.netloc
            and not parsed_url.netloc.endswith(":")
            and not any(character.isspace() for character in url)
            and not re.search(r"%(?![0-9A-Fa-f]{2})", url)
        )
        port = parsed_url.port
        valid_url = valid_url and (port is None or 1 <= port <= 65535)
    except ValueError:
        valid_url = False

    if not valid_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Twilio signature verification requires a valid public HTTPS callback URL."
        )

    if not signature_header:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing X-Twilio-Signature header"
        )

    # Twilio signature calculation: URL + concatenated key-value pairs sorted alphabetically by key
    s = url
    for k in sorted(params.keys()):
        s += f"{k}{params[k]}"

    mac = hmac.new(auth_token.encode("utf-8"), s.encode("utf-8"), hashlib.sha1)
    expected_sig = base64.b64encode(mac.digest()).decode("utf-8")

    if not hmac.compare_digest(signature_header, expected_sig):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid Twilio signature"
        )


# ---------------------------------------------------------
# 3. Twilio WhatsApp Webhook Receiver (POST)
# ---------------------------------------------------------
@router.post("/twilio-webhook")
async def receive_twilio_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Receives incoming WhatsApp messages from Twilio Sandbox / Number.
    Returns standard TwiML XML response.
    """
    content_type = (
        request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    )
    if content_type != "application/x-www-form-urlencoded":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Twilio webhook must use application/x-www-form-urlencoded."
        )

    form_data = await request.form()
    params_dict = dict(form_data)
    signature_header = request.headers.get("X-Twilio-Signature")
    verify_twilio_signature(
        config.TWILIO_WEBHOOK_URL, params_dict, signature_header
    )

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
# 4a. WhatsApp Account Linking Endpoints (Citizen Auth)
# ---------------------------------------------------------
@router.post("/link/generate", response_model=GenerateLinkCodeResponse)
def generate_link_code(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Generate a secure one-time code the citizen sends via WhatsApp to link their account.
    Protected: Accessible by authenticated citizens only.
    """
    return WhatsAppLinkService.generate_link_code(db, current_user)


@router.get("/link/status", response_model=LinkStatusResponse)
def get_link_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Return the current WhatsApp link status for the authenticated citizen.
    Protected: Accessible by authenticated citizens only.
    """
    return WhatsAppLinkService.get_link_status(db, current_user)


@router.delete("/link/unlink", response_model=UnlinkResponse)
def unlink_whatsapp(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Remove the WhatsApp link from the authenticated citizen's account.
    Protected: Accessible by authenticated citizens only.
    """
    return WhatsAppLinkService.unlink(db, current_user)


# ---------------------------------------------------------
# 4. Generate Household QR Code & Direct Link (POST)
# ---------------------------------------------------------
@router.post("/generate-qr")
def generate_household_qr(
    payload: dict,
    current_admin: User = Depends(get_current_admin_user)
):
    """
    Generates household QR payload and direct WhatsApp launch link.
    Protected: Accessible exclusively by authorized municipal administrators.
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
    List registered WhatsApp citizen households in Dhule.
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
    {"phone": "919876543210", "message": "hey", "type": "text"}
    """
    if normalize_environment(config.ENV) == "production":
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
