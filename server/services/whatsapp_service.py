import json
import logging
import re
import secrets
import string
import hashlib
import math
import httpx
from typing import Optional
from urllib.parse import urlsplit
from datetime import datetime, date, timezone, timedelta
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_, inspect
from server.utils.config import config
from server.models.whatsapp_session import WhatsAppCitizen
from server.models.complaint import Complaint
from server.models.task import DriverTask
from server.models.user import User
from server.models.event_report import EventReport
from server.services.media_storage import get_media_storage
from server.services.complaint_service import _is_tracking_number_collision

logger = logging.getLogger(__name__)

# Shared alphabet for tracking IDs: uppercase alphanumeric minus ambiguous I and O.
_ID_ALPHABET = (string.ascii_uppercase + string.digits).translate(
    str.maketrans("", "", "IO")
)
_ID_SUFFIX_LEN = 9
_WA_MAX_RETRIES = 5

_EVENT_CATEGORIES = (
    ("PUBLIC", "🎉 सार्वजनिक / Public", "सार्वजनिक कार्यक्रम / Public Event"),
    ("RELIGIOUS", "🙏 धार्मिक / Religious", "धार्मिक कार्यक्रम / Religious Event"),
    ("WEDDING", "💍 लग्न / Wedding", "लग्न समारंभ / Wedding"),
    ("FESTIVAL", "🎊 उत्सव / Festival", "उत्सव / Festival"),
    ("SCHOOL", "🏫 शाळा / School", "कॉलेज किंवा शाळेचा कार्यक्रम / College or School Event"),
    ("CLEANUP", "🧹 स्वच्छता / Clean-up", "स्वच्छता अभियान / Clean-up Drive"),
    ("OTHER", "📌 इतर / Other", "इतर कार्यक्रम / Other Event"),
)


def _generate_event_reference_id() -> str:
    """Generate a collision-resistant WhatsApp public event reference ID.

    Format: EVT-<YEAR>-<8 uppercase alphanumeric chars>
    Total length: 17 chars — fits String(32).
    """
    year = datetime.now(timezone.utc).year
    suffix = "".join(secrets.choice(_ID_ALPHABET) for _ in range(8))
    return f"EVT-{year}-{suffix}"


def _is_column_in_table(db: Session, table_name: str, column_name: str) -> bool:
    """Check whether a column actually exists in the database table schema."""
    try:
        bind = db.get_bind()
        insp = inspect(bind)
        cols = {c["name"] for c in insp.get_columns(table_name)}
        return column_name in cols
    except Exception:
        return False


def _generate_whatsapp_tracking_id(ward: str) -> str:
    """Generate a collision-resistant WhatsApp complaint tracking number.

    Format: <PREFIX><YEAR>-W<ward_number>-<9 uppercase alphanumeric chars>
    Example: DHL-2026-W12-A7BZ3XKQR
    Total length: ≤ 28 chars — fits String(30).
    """
    prefix = getattr(config, "TRACKING_PREFIX", "DHL-").rstrip("-") + "-"
    ward_num = ward.replace("Ward ", "").strip() if ward else "0"
    year = datetime.now(timezone.utc).year
    suffix = "".join(secrets.choice(_ID_ALPHABET) for _ in range(_ID_SUFFIX_LEN))
    return f"{prefix}{year}-W{ward_num}-{suffix}"


class MediaValidationError(Exception):
    """Raised when an incoming WhatsApp media fails validation rules."""
    pass


class RetryableWhatsAppError(Exception):
    """Raised when Meta is temporarily unavailable and webhook redelivery is useful."""
    pass


def _is_trusted_meta_media_url(url: str) -> bool:
    try:
        parsed = urlsplit(url)
        hostname = (parsed.hostname or "").lower().rstrip(".")
        trusted_domain = (
            hostname == "lookaside.fbsbx.com"
            or hostname.endswith(".fbcdn.net")
        )
        return (
            parsed.scheme == "https"
            and trusted_domain
            and parsed.username is None
            and parsed.password is None
            and parsed.port in (None, 443)
            and not parsed.fragment
        )
    except ValueError:
        return False


def validate_image_content(
    content: bytes,
    declared_mime_type: str = None,
    max_size: int = None
) -> tuple[str, str]:
    """
    Validates binary content against size limits, supported MIME types, and file magic numbers.
    Returns (detected_mime_type, file_extension).
    Allowed formats: JPEG (image/jpeg), PNG (image/png), WebP (image/webp).
    """
    if not content:
        raise MediaValidationError("Empty media file received")

    size_limit = max_size if max_size is not None else config.MAX_UPLOAD_SIZE
    if len(content) > size_limit:
        raise MediaValidationError(f"File size ({len(content)} bytes) exceeds maximum limit of {size_limit} bytes")

    if len(content) < 12:
        raise MediaValidationError("Corrupted or truncated image content (less than 12 bytes)")

    # Magic byte inspection
    detected_mime = None
    ext = None

    if content[:3] == b"\xff\xd8\xff":
        detected_mime = "image/jpeg"
        ext = ".jpg"
    elif content[:8] == b"\x89PNG\r\n\x1a\n":
        detected_mime = "image/png"
        ext = ".png"
    elif content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        detected_mime = "image/webp"
        ext = ".webp"
    else:
        raise MediaValidationError("Unsupported image format. Allowed formats: JPEG, PNG, WebP.")

    # Validate declared MIME type from Meta metadata if supplied
    if declared_mime_type:
        norm_declared = declared_mime_type.strip().lower()
        allowed_mimes = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
        if norm_declared not in allowed_mimes:
            raise MediaValidationError(f"Declared MIME type '{declared_mime_type}' is not an allowed image format.")

        # Check agreement between declared and binary magic bytes
        if norm_declared in ("image/jpeg", "image/jpg") and detected_mime != "image/jpeg":
            raise MediaValidationError("Image binary format does not match declared JPEG MIME type.")
        elif norm_declared == "image/png" and detected_mime != "image/png":
            raise MediaValidationError("Image binary format does not match declared PNG MIME type.")
        elif norm_declared == "image/webp" and detected_mime != "image/webp":
            raise MediaValidationError("Image binary format does not match declared WebP MIME type.")

    return detected_mime, ext


# ---------------------------------------------------------------------------
# Bilingual UI Strings — EcoPulse AI · Dhule Municipal Waste Management
# ---------------------------------------------------------------------------
def _build_texts() -> dict:
    frontend_url = getattr(config, "FRONTEND_URL", "https://ecopulse-ai-frontend.onrender.com/").rstrip("/") + "/"
    muni_mr = getattr(config, "MUNICIPALITY_NAME_MR", "धुळे महानगरपालिका स्वच्छता व्यवस्थापन")
    muni_en = getattr(config, "MUNICIPALITY_NAME", "Dhule Municipal Waste Management")

    onboarding_mr = (
        "नमस्कार! 👋\n\n"
        f"इकोपल्स AI — {muni_mr}ामध्ये आपले स्वागत आहे.\n\n"
        "ही सेवा वापरण्यासाठी प्रथम EcoPulse AI वेबसाइटवर नागरिक म्हणून नोंदणी करा:\n"
        f"🌐 {frontend_url}\n\n"
        "1. वेबसाइट उघडा आणि लॉगिन करा.\n"
        "2. Citizen Dashboard मधील Connect WhatsApp पर्याय निवडा.\n"
        "3. मिळालेला verification code आपल्या WhatsApp वर पाठवा:\n\n"
        "LINK <code>\n\n"
        "आपले WhatsApp खाते सुरक्षितपणे लिंक झाल्यानंतर आपण सर्व नागरिक सेवा वापरू शकता."
    )

    onboarding_en = (
        "Hello! 👋\n\n"
        f"Welcome to EcoPulse AI — {muni_en}.\n\n"
        "To use this service, please first register as a citizen on the EcoPulse AI website:\n"
        f"🌐 {frontend_url}\n\n"
        "1. Open the website and log in.\n"
        "2. Select 'Connect WhatsApp' on your Citizen Dashboard.\n"
        "3. Send the received verification code to this WhatsApp:\n\n"
        "LINK <code>\n\n"
        "Once your WhatsApp account is securely linked, you can access all civic municipal services."
    )

    return {
        "mr": {
            "unauthorized": onboarding_mr,
            "not_linked_prompt": onboarding_mr,
            "linked_welcome": (
                "✅ *धुळे EcoPulse AI — खाते यशस्वीरित्या जोडले!*\n\n"
                "नमस्कार {name}! 🎉\n"
                "आपला WhatsApp नंबर आपल्या EcoPulse खात्याशी जोडला गेला आहे.\n\n"
                "🪙 *ईको-कॉइन्स शिल्लक: {coins} गुण*\n\n"
                "कृपया खालीलपैकी पर्याय निवडा:"
            ),
            "authorized_welcome": (
                f"🏛️ *इकोपल्स AI — {muni_mr}*\n\n"
                "नमस्कार {name}! 👋\n"
                "✅ आपले EcoPulse खाते सक्रिय आहे.\n\n"
                "🪙 *ईको-कॉइन्स शिल्लक: {coins} गुण (₹{rupees} कर सवलत)*\n\n"
                "कृपया खालीलपैकी पर्याय निवडा:"
            ),
            "menu_options": (
                "1️⃣ 🗑️ *कचरा नोंदवा / Report Waste*\n"
                "2️⃣ ⚠️ *सामान्य तक्रार / General Complaint*\n"
                "3️⃣ 🚛 *घंटागाडी ट्रॅकिंग / Garbage Vehicle Tracking*\n"
                "4️⃣ 📅 *संकलन वेळापत्रक / Collection Schedule*\n"
                "5️⃣ 🪙 *इको-वॉलेट आणि रिवॉर्ड्स / EcoWallet & Rewards*\n"
                "6️⃣ 📋 *माझ्या तक्रारी / My Complaints*\n"
                "7️⃣ 📢 *महापालिका सूचना / Municipal Notices*\n"
                "8️⃣ ❓ *मदत आणि भाषा / Help & Change Language*\n\n"
                "👉 *क्रमांक (1-8) किंवा keyword पाठवा / Reply with a number (1-8) or keyword.*"
            ),
            "ask_photo": (
                "📸 *कचरा तक्रार नोंदणी*\n\n"
                "कृपया कचऱ्याचा, घाणीचा किंवा ओव्हरफ्लो झालेल्या कुंडीचा *फोटो पाठवा*."
            ),
            "photo_received_ack": (
                "📸 *फोटो प्राप्त झाला! / Photo received!* ✅\n\n"
                "कचऱ्याचे स्थान निश्चित करण्यासाठी कृपया खालील बटण दाबून आपले Live Location पाठवा किंवा पत्ता टाईप करा."
            ),
            "ask_location": (
                "📍 *कचऱ्याचे स्थान पाठवा / Send Location*\n\n"
                "कृपया खालील 'Send Location' बटण दाबून आपले अचूक GPS लोकेशन पाठवा. आपण पत्ता लिहूनही पाठवू शकता (उदा. 'पत्ता: स्टेशन रोड, धुळे')."
            ),
            "invalid_location": (
                "⚠️ वैध स्थान मिळाले नाही. कृपया अटॅचमेंट (+) मधून आपले सध्याचे WhatsApp Location पुन्हा पाठवा किंवा 'पत्ता: ...' लिहून पाठवा."
            ),
            "report_success": (
                "✅ *तक्रार यशस्वीरित्या नोंदवली गेली!*\n\n"
                "🎫 *तक्रार क्र.:* #{ticket}\n"
                "📍 *स्थान:* {location}\n"
                "🚛 *नियुक्त गाडी:* {driver}\n"
                "⏱️ *निराकरण कालावधी:* ४ तासांच्या आत\n\n"
                "🎉 *अभिनंदन!* शहर स्वच्छ ठेवण्यासाठी आपल्याला *+20 ईको-कॉइन्स* मिळाले आहेत!\n"
                "एकूण शिल्लक: *{coins} गुण*."
            ),
            "complaint_created": (
                "✅ *कचरा तक्रार यशस्वीरित्या नोंदवली गेली आहे!*\n\n"
                "📋 तक्रार क्रमांक / Ticket ID: *{ticket}*\n"
                "🗑️ प्रकार: {type}\n"
                "🚛 नियुक्त स्वच्छता कर्मचारी: *{driver}*\n\n"
                "🎉 बक्षीस: धुळे स्वच्छ ठेवल्याबद्दल तुम्हाला *+20 EcoCoins* मिळाले आहेत!\n\n"
                "घंटागाडी लवकरच कचरा संकलनासाठी पोहोचेल."
            ),
            "general_complaint_prompt": (
                "📝 *सामान्य तक्रार*\n\n"
                "कृपया आपली तक्रार थोडक्यात लिहा (रस्ता, पाणी, दिवे, अतिक्रमण इ.).\n"
                "उदा: *मेन रोडवर मोठा खड्डा आहे, दुरुस्ती आवश्यक आहे.*"
            ),
            "general_complaint_received": (
                "✅ *सामान्य तक्रार नोंदवली गेली आहे!*\n\n"
                "📋 तक्रार क्रमांक: *{ticket}*\n"
                "📝 तपशील: {description}\\n"
                "🚛 नियुक्त अधिकारी / कर्मचारी: *{driver}*\n\n"
                "🎉 तक्रार नोंदवल्याबद्दल आपल्याला *+10 EcoCoins* मिळाले आहेत!\n"
                "संबंधित विभागामार्फत लवकरच कार्यवाही केली जाईल."
            ),
            "no_complaints": (
                "🔍 आपल्या खात्याशी सध्या कोणतीही प्रलंबित तक्रार नाही. परिसर स्वच्छ आहे! 🌟"
            ),
            "complaints_header": "🔍 *आपल्या तक्रारींची सद्यस्थिती:*\n\n",
            "wallet_info": (
                "🪙 *धुळे ईको-वॉलेट (EcoCoin Wallet)*\n\n"
                "शिल्लक गुण: *{coins} EcoCoins*\n"
                "अंदाजे मूल्य: *₹{rupees}*\n\n"
                "🎁 *सवलत पर्याय:*\n"
                "• ५० कॉइन्स = ₹२५ घरपट्टी (Property Tax) सवलत\n"
                "• १०० कॉइन्स = १ महिना धुळे मोफत वाचनालय पास\n"
                "• २०० कॉइन्स = २ मोफत फळझाडे रोपे (महानगरपालिका नर्सरी)\n\n"
                "अधिक माहितीसाठी धुळे महानगरपालिका कर कक्षाशी संपर्क साधा."
            ),
            "truck_unavailable": (
                "🚛 *घंटागाडी थेट ट्रॅकिंग*\n\n"
                "⚠️ सध्या थेट GPS ट्रॅकिंग उपलब्ध नाही.\n"
                "कृपया आपल्या प्रभाग कार्यालयाशी संपर्क साधा किंवा नंतर पुन्हा प्रयत्न करा.\n\n"
                "📞 धुळे महानगरपालिका हेल्पलाइन: 0562-XXXXXX"
            ),
            "schedule_unavailable": (
                "🗓️ *कचरा संकलन वेळापत्रक*\n\n"
                "⚠️ आपल्या भागाचे डिजिटल वेळापत्रक अद्याप उपलब्ध नाही.\n"
                "कृपया आपल्या प्रभाग कार्यालयाशी संपर्क साधा.\n\n"
                "📞 धुळे महानगरपालिका: 0562-XXXXXX"
            ),
            "notices_unavailable": (
                "📢 *धुळे महानगरपालिका सूचना*\n\n"
                "⚠️ सध्या कोणतीही नवीन अधिकृत सूचना नाही.\n"
                "स्वच्छता मोहीम नियमितपणे सुरू आहे. परिसर स्वच्छ ठेवा! 🌿"
            ),
            "help_text": (
                "❓ *धुळे महानगरपालिका स्वच्छता हेल्पलाइन*\n\n"
                "📞 टोल फ्री क्र.: 1800-XXX-XXXX\n"
                "📧 ईमेल: contact@dhulecorporation.gov.in\n"
                "🌐 पोर्टल: ecopulse-ai.gov.in\n\n"
                "🌐 *भाषा बदला / Change Language:*\n"
                "• English साठी 'ENGLISH' टाईप करा.\n"
                "• मराठीसाठी 'MARATHI' टाईप करा.\n"
                "• सार्वजनिक कार्यक्रम नोंदणीसाठी 'EVENT' टाईप करा."
            ),
            "image_error": "⚠️ फोटो स्वीकारता आला नाही. कृपया स्पष्ट JPEG, PNG किंवा WebP फोटो पुन्हा पाठवा.",
            "link_prompt": (
                "🔗 *WhatsApp खाते जोडणी*\n\n"
                "आपल्या Citizen Portal वरून मिळालेला कोड खालील स्वरूपात पाठवा:\n\n"
                "LINK <code>\n\n"
                "उदा: LINK 123456"
            ),
            "link_invalid": (
                "❌ *कोड अवैध किंवा कालबाह्य झाला.*\n\n"
                "कृपया EcoPulse वेबसाइटवर पुन्हा लॉगिन करा आणि नवीन कोड मिळवा:\n"
                f"🌐 {frontend_url}"
            ),
            "event_category_prompt": (
                "🎉 *सार्वजनिक कार्यक्रम नोंदणी / Public Event Reporting*\n\n"
                "कृपया कार्यक्रमाचा प्रकार निवडा / Please select the event category:"
            ),
            "event_ask_date": (
                "📅 *कार्यक्रमाची तारीख / Event Date*\n\n"
                "कृपया कार्यक्रमाची तारीख DD/MM/YYYY स्वरूपात पाठवा (उदा. 25/12/2026).\n"
                "Please enter the event date in DD/MM/YYYY format (e.g. 25/12/2026)."
            ),
            "event_ask_time": (
                "⏰ *कार्यक्रमाची वेळ / Event Time*\n\n"
                "कृपया कार्यक्रमाची सुरुवात वेळ पाठवा (उदा. 06:00 PM किंवा 18:00).\n"
                "Please enter the event start time (e.g. 06:00 PM or 18:00)."
            ),
            "event_ask_location": (
                "📍 *कार्यक्रमाचे ठिकाण / Event Venue*\n\n"
                "कृपया कार्यक्रमाच्या जागेचे Location Pin पाठवा किंवा पत्ता पाठवा (उदा. 'पत्ता: साक्री रोड, धुळे').\n"
                "Please send the event venue location pin or type 'ADDRESS: ...'."
            ),
            "event_summary": (
                "📋 *सार्वजनिक कार्यक्रम नोंदणी सारांश / Event Summary*\n\n"
                "🎉 प्रकार: {category}\n"
                "📅 तारीख: {date}\n"
                "⏰ वेळ: {time}\n"
                "📍 ठिकाण: {location}\n\n"
                "कृपया माहिती बरोबर असल्यास 'Confirm' करा किंवा रद्द करण्यासाठी 'Cancel' करा."
            ),
            "event_success": (
                "✅ *सार्वजनिक कार्यक्रम यशस्वीरित्या नोंदवला गेला!*\n\n"
                "🎫 संदर्भ क्र. (Reference ID): *{ref_id}*\n"
                "📅 तारीख: {date} | ⏰ वेळ: {time}\n"
                "📍 ठिकाण: {location}\n\n"
                "महानगरपालिका स्वच्छता पथकास आगाऊ सूचना देण्यात आली आहे. धन्यवाद! 🌱"
            ),
            "event_cancelled": "❌ कार्यक्रम नोंदणी रद्द करण्यात आली आहे. / Event reporting cancelled."
        },
        "en": {
            "unauthorized": onboarding_en,
            "not_linked_prompt": onboarding_en,
            "linked_welcome": (
                "✅ *Dhule EcoPulse AI — Account Linked Successfully!*\n\n"
                "Hello {name}! 🎉\n"
                "Your WhatsApp number has been linked to your EcoPulse citizen account.\n\n"
                "🪙 *EcoCoins Balance: {coins} pts*\n\n"
                "Please choose an option below:"
            ),
            "authorized_welcome": (
                f"🏛️ *EcoPulse AI — {muni_en}*\n\n"
                "Hello {name}! 👋\n"
                "✅ Your EcoPulse account is active.\n\n"
                "🪙 *EcoCoin Balance: {coins} pts (₹{rupees} rebate)*\n\n"
                "Please choose an option below:"
            ),
            "menu_options": (
                "1️⃣ 🗑️ *Report Waste / कचरा नोंदवा*\n"
                "2️⃣ ⚠️ *General Complaint / सामान्य तक्रार*\n"
                "3️⃣ 🚛 *Garbage Vehicle Tracking / घंटागाडी ट्रॅकिंग*\n"
                "4️⃣ 📅 *Collection Schedule / संकलन वेळापत्रक*\n"
                "5️⃣ 🪙 *EcoWallet & Rewards / इको-वॉलेट आणि रिवॉर्ड्स*\n"
                "6️⃣ 📋 *My Complaints / माझ्या तक्रारी*\n"
                "7️⃣ 📢 *Municipal Notices / महापालिका सूचना*\n"
                "8️⃣ ❓ *Help & Change Language / मदत आणि भाषा*\n\n"
                "👉 *Reply with a number (1-8) or keyword / क्रमांक (1-8) किंवा keyword पाठवा.*"
            ),
            "ask_photo": (
                "📸 *Report Waste Complaint*\n\n"
                "Please send a clear *photo* of the garbage, debris, or overflowing bin."
            ),
            "photo_received_ack": (
                "📸 *Photo received! / फोटो प्राप्त झाला!* ✅\n\n"
                "Please share your location to pinpoint the waste spot."
            ),
            "ask_location": (
                "📍 *Send Location / कचऱ्याचे स्थान पाठवा*\n\n"
                "Please tap 'Send Location' below to share your GPS location, or type an address (e.g. 'Address: Station Road, Dhule')."
            ),
            "invalid_location": (
                "⚠️ Valid location not received. Please resend your current WhatsApp Location via attachment (+) or reply with 'ADDRESS: ...'."
            ),
            "report_success": (
                "✅ *Complaint Registered Successfully!*\n\n"
                "🎫 *Ticket #:* #{ticket}\n"
                "📍 *Location:* {location}\n"
                "🚛 *Assigned Vehicle:* {driver}\n"
                "⏱️ *Resolution SLA:* Within 4 hours\n\n"
                "🎉 *Congratulations!* You earned *+20 EcoCoins* for keeping the city clean!\n"
                "Total Balance: *{coins} pts*."
            ),
            "complaint_created": (
                "✅ *Waste Complaint Registered Successfully!*\n\n"
                "📋 Ticket ID / तक्रार क्र.: *{ticket}*\n"
                "🗑️ Category: {type}\n"
                "🚛 Assigned Sanitation Staff: *{driver}*\n\n"
                "🎉 *Reward:* You earned *+20 EcoCoins* for keeping Dhule clean!\n\n"
                "A collection vehicle is scheduled to be dispatched to this location."
            ),
            "general_complaint_prompt": (
                "📝 *General Civic Complaint*\n\n"
                "Please describe your issue briefly (roads, water, streetlights, encroachment, etc.).\n"
                "Example: *Large pothole near City Hospital, urgent repair needed.*"
            ),
            "general_complaint_received": (
                "✅ *General Complaint Registered!*\n\n"
                "📋 Ticket ID: *{ticket}*\n"
                "📝 Details: {description}\n"
                "🚛 Assigned Officer / Staff: *{driver}*\n\n"
                "🎉 You earned *+10 EcoCoins* for filing this report!\n"
                "The respective municipal department has been notified."
            ),
            "no_complaints": (
                "🔍 No active complaints found for your account. Everything is clean and green! 🌟"
            ),
            "complaints_header": "🔍 *Your Recent Complaints Status:*\n\n",
            "wallet_info": (
                "🪙 *EcoWallet & Rewards (EcoCoins)*\n\n"
                "Balance: *{coins} EcoCoins*\n"
                "Estimated Value: *₹{rupees}*\n\n"
                "🎁 *Rebate Options:*\n"
                "• 50 Coins = ₹25 Property Tax Rebate\n"
                "• 100 Coins = 1 Month Free City Library Pass\n"
                "• 200 Coins = 2 Free Fruit Tree Saplings (Municipal Nursery)\n\n"
                "Contact Dhule Municipal Corporation Tax Cell for more details."
            ),
            "truck_unavailable": (
                "🚛 *Garbage Vehicle Live Tracking*\n\n"
                "⚠️ Live GPS tracking is currently unavailable for this vehicle.\n"
                "Please contact your ward office or try again shortly.\n\n"
                "📞 Dhule Municipal Helpline: 0562-XXXXXX"
            ),
            "schedule_unavailable": (
                "🗓️ *Waste Collection Schedule*\n\n"
                "⚠️ Digital schedule for your ward is not yet online.\n"
                "Please contact your local ward office for collection timings.\n\n"
                "📞 Dhule Municipal Corporation: 0562-XXXXXX"
            ),
            "notices_unavailable": (
                "📢 *Municipal Notices*\n\n"
                "⚠️ No new official municipal notices at this time.\n"
                "City cleanliness drive is active. Keep Dhule green and clean! 🌿"
            ),
            "help_text": (
                "❓ *Dhule Municipal Waste Helpline*\n\n"
                "📞 Toll Free: 1800-XXX-XXXX\n"
                "📧 Email: contact@dhulecorporation.gov.in\n"
                "🌐 Portal: ecopulse-ai.gov.in\n\n"
                "🌐 *Switch Language:*\n"
                "• Type 'MARATHI' for Marathi / मराठी.\n"
                "• Type 'ENGLISH' for English.\n"
                "• Type 'EVENT' to report a public event."
            ),
            "image_error": "⚠️ Could not accept the photo. Please resend a clear JPEG, PNG, or WebP image.",
            "link_prompt": (
                "🔗 *Link WhatsApp Account*\n\n"
                "Send your verification code from the Citizen Portal in this format:\n\n"
                "LINK <code>\n\n"
                "Example: LINK 123456"
            ),
            "link_invalid": (
                "❌ *Invalid or expired code.*\n\n"
                "Please log in to the EcoPulse website and generate a new code:\n"
                f"🌐 {frontend_url}"
            ),
            "event_category_prompt": (
                "🎉 *Public Event Reporting / सार्वजनिक कार्यक्रम नोंदणी*\n\n"
                "Please select the event category / कृपया कार्यक्रमाचा प्रकार निवडा:"
            ),
            "event_ask_date": (
                "📅 *Event Date / कार्यक्रमाची तारीख*\n\n"
                "Please enter the event date in DD/MM/YYYY format (e.g. 25/12/2026).\n"
                "कृपया कार्यक्रमाची तारीख DD/MM/YYYY स्वरूपात पाठवा (उदा. 25/12/2026)."
            ),
            "event_ask_time": (
                "⏰ *Event Time / कार्यक्रमाची वेळ*\n\n"
                "Please enter the event start time (e.g. 06:00 PM or 18:00).\n"
                "कृपया कार्यक्रमाची सुरुवात वेळ पाठवा (उदा. 06:00 PM किंवा 18:00)."
            ),
            "event_ask_location": (
                "📍 *Event Venue / कार्यक्रमाचे ठिकाण*\n\n"
                "Please share the event venue location pin or type 'ADDRESS: ...'.\n"
                "कृपया कार्यक्रमाच्या जागेचे Location Pin पाठवा किंवा पत्ता पाठवा."
            ),
            "event_summary": (
                "📋 *Event Summary / सार्वजनिक कार्यक्रम सारांश*\n\n"
                "🎉 Category: {category}\n"
                "📅 Date: {date}\n"
                "⏰ Time: {time}\n"
                "📍 Location: {location}\n\n"
                "Please confirm if the details are correct or cancel."
            ),
            "event_success": (
                "✅ *Public Event Registered Successfully!*\n\n"
                "🎫 Reference ID: *{ref_id}*\n"
                "📅 Date: {date} | ⏰ Time: {time}\n"
                "📍 Location: {location}\n\n"
                "Municipal sanitation team has been notified in advance. Thank you! 🌱"
            ),
            "event_cancelled": "❌ Event reporting cancelled. / कार्यक्रम नोंदणी रद्द केली."
        }
    }


class WhatsAppService:
    """Core service for managing bilingual WhatsApp interactions with Dhule citizens."""

    @staticmethod
    def normalize_phone(phone: str) -> str:
        """Strip non-digit chars and ensure E.164-compatible national or international format."""
        digits = re.sub(r'\D', '', phone or '')
        return digits

    @staticmethod
    def get_or_create_citizen(db: Session, phone: str) -> WhatsAppCitizen:
        """Fetch existing WhatsApp citizen session or create a new IDLE record."""
        normalized = WhatsAppService.normalize_phone(phone)
        citizen = db.query(WhatsAppCitizen).filter(
            WhatsAppCitizen.phone_number == normalized
        ).first()

        if not citizen:
            citizen = WhatsAppCitizen(
                phone_number=normalized,
                full_name="Dhule Citizen",
                ward="Dhule Ward 1",
                is_authorized=False,
                preferred_language="mr",
                eco_coins=100,
                conversation_state="IDLE"
            )
            db.add(citizen)
            db.commit()
            db.refresh(citizen)
        elif citizen.full_name == "Shirpur Resident":
            citizen.full_name = "Dhule Citizen"
            db.commit()
        return citizen

    @staticmethod
    def find_matching_citizen_user(db: Session, sender_phone: str) -> Optional[User]:
        if not sender_phone:
            return None
        norm = WhatsAppService.normalize_phone(sender_phone)
        if not norm or len(norm) < 10:
            return None

        candidate_phones = {norm, f"+{norm}"}
        if norm.startswith("91") and len(norm) == 12:
            local_10 = norm[2:]
            candidate_phones.add(local_10)
            candidate_phones.add(f"+91{local_10}")

        user_filters = [
            User.phone.in_(candidate_phones),
            User.role == "citizen",
            User.is_active == True
        ]
        if _is_column_in_table(db, "users", "is_locked") and hasattr(User, "is_locked"):
            user_filters.append(getattr(User, "is_locked").is_(False))
        if _is_column_in_table(db, "users", "account_status") and hasattr(User, "account_status"):
            user_filters.append(getattr(User, "account_status") == "active")
        if _is_column_in_table(db, "users", "is_verified") and hasattr(User, "is_verified"):
            user_filters.append(getattr(User, "is_verified").is_(True))

        matches = db.query(User).filter(*user_filters).all()

        valid_matches = [
            u for u in matches
            if u.phone and u.phone.strip() and u.phone in candidate_phones
        ]

        if len(valid_matches) == 1:
            return valid_matches[0]
        elif len(valid_matches) > 1:
            logger.warning("[WHATSAPP IDENTITY] Ambiguous citizen phone match (%d accounts).", len(valid_matches))
            return None
        return None

    @staticmethod
    def select_eligible_driver(db: Session) -> Optional[User]:
        """
        Selects an eligible registered driver using deterministic least-active-workload.
        Workload = count of tasks with status 'Pending' or 'In Progress'.
        Ties are broken deterministically by driver.id ascending.
        Returns None if no eligible driver is available.
        """
        driver_filters = [
            User.role == "driver",
            User.is_active == True
        ]
        if _is_column_in_table(db, "users", "is_locked") and hasattr(User, "is_locked"):
            driver_filters.append(getattr(User, "is_locked").is_(False))
        if _is_column_in_table(db, "users", "account_status") and hasattr(User, "account_status"):
            driver_filters.append(getattr(User, "account_status") == "active")
        if _is_column_in_table(db, "users", "is_verified") and hasattr(User, "is_verified"):
            driver_filters.append(getattr(User, "is_verified").is_(True))

        eligible_drivers = db.query(User).filter(*driver_filters).all()

        if not eligible_drivers:
            logger.info("[DRIVER ASSIGNMENT] No active registered drivers found; leaving complaint unassigned.")
            return None

        # Calculate active workload for each eligible driver
        driver_workloads = []
        for d in eligible_drivers:
            if d.role != "driver":
                continue
            active_task_count = db.query(DriverTask).filter(
                DriverTask.driver_id == d.id,
                DriverTask.status.in_(["Pending", "In Progress"])
            ).count()
            driver_workloads.append((active_task_count, d.id, d))

        if not driver_workloads:
            return None

        # Sort by least active tasks first, then by driver id ascending (deterministic)
        driver_workloads.sort(key=lambda item: (item[0], item[1]))
        selected_driver = driver_workloads[0][2]
        logger.info(
            f"[DRIVER ASSIGNMENT] Selected driver {selected_driver.full_name} "
            f"(ID: {selected_driver.id}, active tasks: {driver_workloads[0][0]})"
        )
        return selected_driver

    @staticmethod
    def build_main_menu_interactive(lang: str = "mr", greeting_text: str = "") -> dict:
        """Construct a Meta WhatsApp Cloud API interactive list message payload for the 8-option main menu."""
        is_mr = (lang or "mr").lower() == "mr"
        header_text = "🏛️ EcoPulse AI"
        footer_text = "धुळे महानगरपालिका" if is_mr else "Dhule Municipal Corporation"
        button_label = "मेनू उघडा" if is_mr else "Main Menu"
        section_title = "नागरी सेवा" if is_mr else "Civic Services"

        menu_rows = [
            {
                "id": "MENU_REPORT_WASTE",
                "title": "🗑️ कचरा / Report Waste"[:24],
                "description": "कचरा तक्रार नोंदवा / Report waste"[:72]
            },
            {
                "id": "MENU_GENERAL_COMPLAINT",
                "title": "⚠️ तक्रार / Complaint"[:24],
                "description": "सामान्य तक्रार / General complaint"[:72]
            },
            {
                "id": "MENU_VEHICLE_TRACKING",
                "title": "🚛 घंटागाडी / Tracking"[:24],
                "description": "घंटागाडी ट्रॅकिंग / Vehicle tracking"[:72]
            },
            {
                "id": "MENU_COLLECTION_SCHEDULE",
                "title": "📅 वेळापत्रक / Schedule"[:24],
                "description": "संकलन वेळापत्रक / Collection schedule"[:72]
            },
            {
                "id": "MENU_ECO_WALLET",
                "title": "🪙 इको-वॉलेट / Rewards"[:24],
                "description": "इको-वॉलेट आणि रिवॉर्ड्स / EcoWallet & rewards"[:72]
            },
            {
                "id": "MENU_MY_COMPLAINTS",
                "title": "📋 तक्रारी / Complaints"[:24],
                "description": "माझ्या तक्रारी तपासा / My complaints status"[:72]
            },
            {
                "id": "MENU_NOTICES",
                "title": "📢 सूचना / Notices"[:24],
                "description": "महानगरपालिका सूचना / Municipal notices"[:72]
            },
            {
                "id": "MENU_HELP_LANG",
                "title": "❓ मदत / Help & Lang"[:24],
                "description": "मदत व भाषा बदला / Help & change language"[:72]
            }
        ]

        body = (greeting_text or "").strip()
        if not body:
            body = (
                "🏛️ *इकोपल्स AI — धुळे महानगरपालिका*\nकृपया खालील मेनूमधून सेवा निवडा:"
                if is_mr
                else "🏛️ *EcoPulse AI — Dhule Municipal Services*\nPlease select a service from the menu:"
            )

        return {
            "type": "list",
            "header": {
                "type": "text",
                "text": header_text[:60]
            },
            "body": {
                "text": body[:1024]
            },
            "footer": {
                "text": footer_text[:60]
            },
            "action": {
                "button": button_label[:20],
                "sections": [
                    {
                        "title": section_title[:24],
                        "rows": [
                            {
                                "id": r["id"][:200],
                                "title": r["title"][:24],
                                "description": r["description"][:72]
                            }
                            for r in menu_rows
                        ]
                    }
                ]
            }
        }

    @staticmethod
    def build_location_request_interactive(prompt_text: str) -> dict:
        """Construct a Meta WhatsApp Cloud API location_request_message payload."""
        return {
            "type": "location_request_message",
            "body": {
                "text": (prompt_text or "")[:1024]
            },
            "action": {
                "name": "send_location"
            }
        }

    @staticmethod
    def send_meta_location_request(
        to_phone: str,
        body_text: str,
        fallback_text: Optional[str] = None
    ) -> dict:
        """Send a native Meta WhatsApp location_request_message with fallback."""
        interactive = WhatsAppService.build_location_request_interactive(body_text)
        return WhatsAppService.send_meta_whatsapp(
            to_phone,
            fallback_text or body_text,
            interactive=interactive
        )

    @staticmethod
    def build_event_categories_interactive(lang: str = "mr") -> dict:
        """Construct a Meta WhatsApp interactive list message for the 7 event categories."""
        is_mr = (lang or "mr").lower() == "mr"
        header_text = "🎉 EcoPulse AI — Events"
        footer_text = "धुळे महानगरपालिका" if is_mr else "Dhule Municipal Corporation"
        button_label = "श्रेणी निवडा" if is_mr else "Select Category"
        section_title = "कार्यक्रम प्रकार" if is_mr else "Event Categories"

        rows = [
            {
                "id": "EVENT_CAT_PUBLIC",
                "title": "🎉 सार्वजनिक / Public"[:24],
                "description": "सार्वजनिक कार्यक्रम / Public Event"[:72]
            },
            {
                "id": "EVENT_CAT_RELIGIOUS",
                "title": "🙏 धार्मिक / Religious"[:24],
                "description": "धार्मिक कार्यक्रम / Religious Event"[:72]
            },
            {
                "id": "EVENT_CAT_WEDDING",
                "title": "💍 लग्न / Wedding"[:24],
                "description": "लग्न समारंभ / Wedding"[:72]
            },
            {
                "id": "EVENT_CAT_FESTIVAL",
                "title": "🎊 उत्सव / Festival"[:24],
                "description": "उत्सव / Festival"[:72]
            },
            {
                "id": "EVENT_CAT_SCHOOL",
                "title": "🏫 शाळा / School"[:24],
                "description": "कॉलेज किंवा शाळेचा कार्यक्रम / College or School Event"[:72]
            },
            {
                "id": "EVENT_CAT_CLEANUP",
                "title": "🧹 स्वच्छता / Clean-up"[:24],
                "description": "स्वच्छता अभियान / Clean-up Drive"[:72]
            },
            {
                "id": "EVENT_CAT_OTHER",
                "title": "📌 इतर / Other"[:24],
                "description": "इतर कार्यक्रम / Other Event"[:72]
            }
        ]

        return {
            "type": "list",
            "header": {
                "type": "text",
                "text": header_text[:60]
            },
            "body": {
                "text": "कृपया कार्यक्रमाचा प्रकार निवडा / Please select the event category:"[:1024]
            },
            "footer": {
                "text": footer_text[:60]
            },
            "action": {
                "button": button_label[:20],
                "sections": [
                    {
                        "title": section_title[:24],
                        "rows": rows
                    }
                ]
            }
        }

    @staticmethod
    def parse_and_validate_event_date(date_str: str) -> tuple[bool, Optional[date], Optional[str]]:
        """Validate event date in DD/MM/YYYY format and reject past dates."""
        cleaned = (date_str or "").strip()
        match = re.match(r'^\s*(\d{1,2})[/-](\d{1,2})[/-](\d{4})\s*$', cleaned)
        if not match:
            return False, None, "Invalid format. Expected DD/MM/YYYY (e.g. 25/12/2026)."
        try:
            day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
            parsed = date(year, month, day)
        except (ValueError, OverflowError):
            return False, None, "Invalid calendar date."
        today = datetime.now(timezone.utc).date()
        if parsed < today:
            return False, None, "Event date cannot be in the past."
        return True, parsed, None

    @staticmethod
    def parse_and_validate_event_time(time_str: str) -> tuple[bool, Optional[str], Optional[str]]:
        """Validate event time in 12-hour or 24-hour format."""
        cleaned = (time_str or "").strip()
        formats = [
            "%I:%M %p",
            "%I:%M%p",
            "%I %p",
            "%I%p",
            "%H:%M",
            "%H",
        ]
        for fmt in formats:
            try:
                t = datetime.strptime(cleaned.upper(), fmt).time()
                return True, t.strftime("%I:%M %p"), None
            except ValueError:
                pass
        return False, None, "Invalid time format. Example: 06:00 PM or 18:00."

    @staticmethod
    def build_quick_buttons_interactive(
        body_text: str,
        buttons: list,
        header_text: Optional[str] = None,
        footer_text: Optional[str] = None
    ) -> dict:
        """Construct a Meta WhatsApp Cloud API reply button interactive payload (up to 3 buttons)."""
        clean_buttons = []
        for btn in buttons[:3]:
            if isinstance(btn, (list, tuple)) and len(btn) >= 2:
                btn_id, btn_title = str(btn[0]), str(btn[1])
            elif isinstance(btn, dict):
                btn_id = str(btn.get("id", ""))
                btn_title = str(btn.get("title", ""))
            else:
                continue
            clean_buttons.append({
                "type": "reply",
                "reply": {
                    "id": btn_id[:256],
                    "title": btn_title[:20]
                }
            })

        interactive = {
            "type": "button",
            "body": {"text": (body_text or "")[:1024]},
            "action": {"buttons": clean_buttons}
        }
        if header_text:
            interactive["header"] = {"type": "text", "text": header_text[:60]}
        if footer_text:
            interactive["footer"] = {"text": footer_text[:60]}
        return interactive

    @staticmethod
    def send_meta_interactive_list(
        to_phone: str,
        body_text: str,
        button_label: str,
        sections: list,
        header_text: Optional[str] = None,
        footer_text: Optional[str] = None,
        fallback_text: Optional[str] = None
    ) -> dict:
        """Send a native Meta interactive list message with plain text fallback."""
        interactive = {
            "type": "list",
            "body": {"text": (body_text or "")[:1024]},
            "action": {
                "button": (button_label or "Menu")[:20],
                "sections": sections
            }
        }
        if header_text:
            interactive["header"] = {"type": "text", "text": header_text[:60]}
        if footer_text:
            interactive["footer"] = {"text": footer_text[:60]}
        return WhatsAppService.send_meta_whatsapp(
            to_phone=to_phone,
            message_text=fallback_text or body_text,
            interactive=interactive
        )

    @staticmethod
    def send_meta_interactive_buttons(
        to_phone: str,
        body_text: str,
        buttons: list,
        header_text: Optional[str] = None,
        footer_text: Optional[str] = None,
        fallback_text: Optional[str] = None
    ) -> dict:
        """Send native Meta quick-reply buttons (up to 3) with plain text fallback."""
        interactive = WhatsAppService.build_quick_buttons_interactive(
            body_text=body_text,
            buttons=buttons,
            header_text=header_text,
            footer_text=footer_text
        )
        return WhatsAppService.send_meta_whatsapp(
            to_phone=to_phone,
            message_text=fallback_text or body_text,
            interactive=interactive
        )

    @staticmethod
    def send_meta_whatsapp(
        to_phone: str,
        message_text: str,
        buttons: list = None,
        interactive: Optional[dict] = None
    ) -> dict:
        """Send message via official Meta WhatsApp Business Cloud API.
        
        Supports both traditional text messages and native interactive messages (lists and buttons).
        If interactive message delivery fails or is rejected, gracefully falls back to plain text.
        """
        token = config.WHATSAPP_TOKEN
        phone_id = config.WHATSAPP_PHONE_NUMBER_ID
        api_version = config.WHATSAPP_GRAPH_API_VERSION or "v20.0"

        if not token or not phone_id:
            logger.info("[MOCK META WHATSAPP] Outbound message simulated; provider credentials are not configured.")
            return {
                "status": "simulated",
                "type": "interactive" if interactive else "text",
                "interactive": interactive
            }

        url = f"https://graph.facebook.com/{api_version}/{phone_id}/messages"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        if interactive:
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to_phone,
                "type": "interactive",
                "interactive": interactive
            }
        else:
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to_phone,
                "type": "text",
                "text": {"body": message_text}
            }

        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.post(url, headers=headers, json=payload)
                if res.status_code == 400 and interactive and message_text:
                    logger.warning("[META WHATSAPP] Interactive message rejected (HTTP 400); falling back to plain text.")
                    fallback_payload = {
                        "messaging_product": "whatsapp",
                        "recipient_type": "individual",
                        "to": to_phone,
                        "type": "text",
                        "text": {"body": message_text}
                    }
                    fallback_res = client.post(url, headers=headers, json=fallback_payload)
                    fallback_res.raise_for_status()
                    return fallback_res.json()

                res.raise_for_status()
                return res.json()
        except httpx.HTTPStatusError as exc:
            logger.error("[META WHATSAPP] Outbound request failed (HTTP %d).", exc.response.status_code)
            raise RetryableWhatsAppError(
                f"Meta outbound request failed with HTTP {exc.response.status_code}"
            ) from None
        except httpx.TimeoutException:
            logger.warning("[META WHATSAPP] Outbound request timed out.")
            raise RetryableWhatsAppError("Meta outbound request timed out") from None
        except httpx.RequestError as exc:
            logger.warning("[META WHATSAPP] Outbound request failed (%s).", type(exc).__name__)
            raise RetryableWhatsAppError("Meta outbound request failed") from None
        except ValueError:
            logger.error("[META WHATSAPP] Outbound response was not valid JSON.")
            raise RetryableWhatsAppError("Meta returned an invalid outbound response") from None

    @staticmethod
    def fetch_and_store_meta_media(media_id: str) -> dict:
        """
        Executes two-step Meta Graph API media retrieval:
        1. Fetch media metadata (download URL, MIME type, size)
        2. Download binary bytes with Authorization header
        3. Validate binary against allowed types and maximum size
        4. Store safely via media storage abstraction
        """
        token = config.WHATSAPP_TOKEN
        api_version = config.WHATSAPP_GRAPH_API_VERSION or "v20.0"

        if not token:
            logger.warning("[META MEDIA] WHATSAPP_TOKEN is not configured; cannot retrieve image.")
            return {"success": False, "error": "WHATSAPP_TOKEN is not configured"}

        if not media_id or not str(media_id).strip():
            return {"success": False, "error": "Invalid media_id"}

        meta_url = f"https://graph.facebook.com/{api_version}/{media_id}"
        headers = {"Authorization": f"Bearer {token}"}

        try:
            with httpx.Client(timeout=15.0, follow_redirects=False) as client:
                meta_res = client.get(meta_url, headers=headers)
                if meta_res.status_code != 200:
                    retryable = meta_res.status_code == 429 or meta_res.status_code >= 500
                    logger.warning("[META MEDIA] Metadata request failed (HTTP %d).", meta_res.status_code)
                    return {
                        "success": False,
                        "retryable": retryable,
                        "error": f"Meta metadata request failed with HTTP {meta_res.status_code}",
                    }

                try:
                    meta_data = meta_res.json()
                except Exception:
                    logger.error("[META MEDIA] Invalid metadata response from Meta.")
                    return {"success": False, "error": "Invalid metadata response from Meta"}

                download_url = meta_data.get("url")
                if not download_url:
                    logger.error("[META MEDIA] No download URL returned.")
                    return {"success": False, "error": "No download URL returned by Meta"}
                if not _is_trusted_meta_media_url(download_url):
                    logger.error("[META MEDIA] Rejected an untrusted media download host.")
                    return {"success": False, "error": "Untrusted media download URL"}

                try:
                    declared_size = int(meta_data.get("file_size", 0) or 0)
                except (TypeError, ValueError):
                    return {"success": False, "error": "Invalid media size returned by Meta"}
                if declared_size < 0 or declared_size > config.MAX_UPLOAD_SIZE:
                    return {"success": False, "error": "Media exceeds the configured upload limit"}

                declared_mime = meta_data.get("mime_type")

                bin_res = client.get(download_url, headers=headers)
                if bin_res.status_code != 200:
                    retryable = bin_res.status_code == 429 or bin_res.status_code >= 500
                    logger.warning("[META MEDIA] Binary download failed (HTTP %d).", bin_res.status_code)
                    return {
                        "success": False,
                        "retryable": retryable,
                        "error": f"Media binary download failed with HTTP {bin_res.status_code}",
                    }

                content = bin_res.content

            detected_mime, ext = validate_image_content(content, declared_mime_type=declared_mime)
            calc_sha256 = hashlib.sha256(content).hexdigest()

            storage = get_media_storage()
            storage_ref = storage.save_image(
                content=content,
                extension=ext,
                mime_type=detected_mime,
                media_id=media_id
            )

            logger.info("[META MEDIA] Image retrieved, validated, and stored (%d bytes).", len(content))
            return {
                "success": True,
                "storage_ref": storage_ref,
                "mime_type": detected_mime,
                "sha256": calc_sha256,
                "file_size": len(content),
                "media_id": media_id
            }

        except MediaValidationError as e:
            logger.warning("[META MEDIA] Validation rejected image: %s", str(e))
            return {"success": False, "error": str(e)}
        except httpx.TimeoutException:
            logger.warning("[META MEDIA] Request timed out while retrieving image.")
            return {"success": False, "retryable": True, "error": "Connection timed out contacting Meta Graph API"}
        except httpx.RequestError as e:
            logger.warning("[META MEDIA] Request failed (%s).", type(e).__name__)
            return {"success": False, "retryable": True, "error": "Could not retrieve image from Meta"}
        except Exception as e:
            logger.error("[META MEDIA] Unexpected failure processing image (%s).", type(e).__name__)
            return {"success": False, "error": "Internal error processing media"}

    @staticmethod
    def handle_incoming_message(
        db: Session,
        sender_phone: str,
        message_type: str,
        text_body: str = "",
        media_url: str = "",
        media_id: str = "",
        latitude: float = None,
        longitude: float = None,
        message_id: str = None
    ) -> dict:
        """
        Processes inbound messages from WhatsApp citizens.
        Implements:
        - Interactive and numeric menu options (1-8, with 8 options total)
        - Native WhatsApp location request after waste photo submission
        - Manual address fallback in AWAITING_LOCATION
        - Complete public event reporting workflow
        - Existing authentication, citizen matching, driver assignment, and persistence.
        """
        all_texts = _build_texts()
        citizen = WhatsAppService.get_or_create_citizen(db, sender_phone)
        lang = citizen.preferred_language or "mr"
        strings = all_texts.get(lang, all_texts["mr"])

        clean_text = (text_body or "").strip()
        normalized_phone = WhatsAppService.normalize_phone(sender_phone)
        candidate_phones = {normalized_phone, f"+{normalized_phone}"}
        if normalized_phone.startswith("91") and len(normalized_phone) == 12:
            local_10 = normalized_phone[2:]
            candidate_phones.add(local_10)
            candidate_phones.add(f"+91{local_10}")

        # Account status / security check via DB catalog inspection
        blocked_account = None
        if _is_column_in_table(db, "users", "account_status") and hasattr(User, "account_status"):
            blocked_account = db.query(User).filter(
                User.phone.in_(candidate_phones),
                getattr(User, "account_status").in_(["suspended", "retired", "deactivated"]),
            ).first()
        elif _is_column_in_table(db, "users", "is_locked") and hasattr(User, "is_locked"):
            blocked_account = db.query(User).filter(
                User.phone.in_(candidate_phones),
                or_(User.is_active.is_(False), getattr(User, "is_locked").is_(True)),
            ).first()
        else:
            blocked_account = db.query(User).filter(
                User.phone.in_(candidate_phones),
                User.is_active.is_(False),
            ).first()

        if blocked_account:
            citizen.is_authorized = False
            db.commit()
            reply = strings.get("not_linked_prompt", "This account is not available. Contact municipal support.")
            WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
            return {"status": "account_unavailable", "reply": reply}

        # ----------------------------------------------------------------
        # STEP 0a: Detect VERIFY <code> command — Website Registration Verification
        # ----------------------------------------------------------------
        verify_match = re.match(r'^VERIFY(?:\s+(.*))?$', clean_text, re.IGNORECASE)
        if verify_match:
            raw_code = (verify_match.group(1) or "").strip()
            from server.services.whatsapp_verification_service import WhatsAppVerificationService
            result = WhatsAppVerificationService.process_verification_message(
                db=db,
                sender_phone=sender_phone,
                raw_code=raw_code,
                preferred_language=lang
            )
            reply = result["reply"]
            WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
            return {
                "status": result["status"],
                "citizen": citizen.phone_number,
                "reply": reply,
                "verified": result.get("verified", False)
            }

        # ----------------------------------------------------------------
        # STEP 0: Detect LINK <code> command
        # ----------------------------------------------------------------
        link_match = re.match(r'^LINK(?:\s+(.*))?$', clean_text, re.IGNORECASE)
        if link_match:
            raw_code = (link_match.group(1) or "").strip()
            if not raw_code:
                reply = strings["link_invalid"]
                WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
                return {"status": "link_failed", "reply": reply}

            from server.services.whatsapp_link_service import WhatsAppLinkService
            linked_user = WhatsAppLinkService.redeem_link_code(db, raw_code, normalized_phone)
            if linked_user:
                db.refresh(citizen)
                reply = strings["linked_welcome"].format(
                    name=linked_user.full_name or linked_user.email or "Citizen",
                    coins=citizen.eco_coins
                ) + "\n\n" + strings["menu_options"]
                WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
                return {"status": "linked", "citizen": citizen.phone_number, "reply": reply}
            else:
                reply = strings["link_invalid"]
                WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
                return {"status": "link_failed", "reply": reply}

        # ----------------------------------------------------------------
        # STEP 0b: Legacy QR code authorization support
        # ----------------------------------------------------------------
        qr_match = re.search(r'(?:JOIN\s+)?(SHP[-_]W(\d+)[-_]H([A-Za-z0-9]+))', clean_text, re.IGNORECASE)
        if qr_match:
            full_code = qr_match.group(1).upper()
            ward_num = qr_match.group(2)
            citizen.household_id = full_code
            citizen.ward = f'Ward {ward_num}'
            citizen.is_authorized = True
            citizen.conversation_state = 'IDLE'
            db.commit()

            reply = strings['authorized_welcome'].format(
                name=citizen.full_name or 'Citizen',
                coins=citizen.eco_coins,
                rupees=citizen.eco_coins // 2
            ) + f"\n📍 प्रभाग: {citizen.ward} | घर क्र.: {citizen.household_id}\n\n" + strings["menu_options"]

            WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
            return {'status': 'authorized', 'citizen': citizen.phone_number, 'reply': reply}

        # ----------------------------------------------------------------
        # STEP 1: Auth gatekeeper — citizen must have user_id or is_authorized
        # ----------------------------------------------------------------
        is_linked = bool(citizen.user_id or citizen.is_authorized)
        if not is_linked:
            reply = strings["not_linked_prompt"]
            WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
            return {"status": "not_linked", "reply": reply}

        lowered = clean_text.lower()
        is_full_menu_cmd = (
            clean_text in {"MENU_FULL_MENU", "FULL_MENU"}
            or lowered == "full menu"
        )
        is_menu_cmd = (
            lowered in {"hey", "hello", "hi", "namaskar", "namaste", "नमस्कार", "start", "menu"}
            or clean_text in {"MENU_MAIN", "MAIN_MENU", "MENU_BACK", "BACK_TO_MENU"}
        )

        def _present_main_menu(extra_note: str = ""):
            c_name = "Citizen"
            if citizen.user_id:
                u_obj = db.query(User).filter(User.id == citizen.user_id).first()
                if u_obj and u_obj.full_name:
                    c_name = u_obj.full_name
            elif citizen.full_name and citizen.full_name != "Shirpur Resident":
                c_name = citizen.full_name

            welcome = strings["authorized_welcome"].format(
                name=c_name,
                coins=citizen.eco_coins,
                rupees=citizen.eco_coins // 2
            )
            if extra_note:
                welcome = extra_note + "\n\n" + welcome

            full_text_menu = (
                "🏛️ *EcoPulse AI — Municipal Services / महानगरपालिका नागरी सेवा*\n\n"
                "नमस्कार! Hello! 👋\n\n"
                f"{welcome}\n\n{strings['menu_options']}"
            )
            WhatsAppService.send_meta_whatsapp(
                citizen.phone_number,
                message_text=full_text_menu
            )
            quick_actions = WhatsAppService.build_quick_buttons_interactive(
                body_text="⚡ झटपट सेवा / Quick Actions",
                buttons=[
                    ("MENU_REPORT_WASTE", "🗑️ कचरा / Waste"),
                    ("MENU_GENERAL_COMPLAINT", "⚠️ तक्रार / Report"),
                    ("MENU_FULL_MENU", "📋 पूर्ण मेनू / Menu")
                ]
            )
            WhatsAppService.send_meta_whatsapp(
                citizen.phone_number,
                message_text="⚡ Quick actions / झटपट सेवा",
                interactive=quick_actions
            )
            return {"status": "menu_presented", "reply": full_text_menu}

        if is_full_menu_cmd:
            interactive_menu = WhatsAppService.build_main_menu_interactive(
                lang=lang,
                greeting_text=(
                    "सेवा निवडा / Select a service"
                    if lang == "mr"
                    else "Select a service / सेवा निवडा"
                )
            )
            WhatsAppService.send_meta_whatsapp(
                citizen.phone_number,
                message_text=strings["menu_options"],
                interactive=interactive_menu
            )
            return {"status": "full_menu_presented", "reply": strings["menu_options"]}

        if is_menu_cmd:
            return _present_main_menu()

        # ----------------------------------------------------------------
        # GLOBAL CANCELLATION: Return to IDLE from any in-flight state
        # ----------------------------------------------------------------
        is_cancel = clean_text in {"CANCEL", "EVENT_CANCEL"} or lowered in {"cancel", "रद्द", "थांबा", "stop"}
        if is_cancel and citizen.conversation_state != "IDLE":
            citizen.conversation_state = "IDLE"
            citizen.pending_complaint_data = None
            db.commit()
            reply = strings["event_cancelled"]
            WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
            return {"status": "event_cancelled", "reply": reply}

        # ----------------------------------------------------------------
        # PUBLIC EVENT REPORTING STATE MACHINE
        # ----------------------------------------------------------------
        if citizen.conversation_state == "AWAITING_EVENT_CATEGORY":
            cat_name = None
            if clean_text in {"EVENT_CAT_PUBLIC", "1"} or "सार्वजनिक" in lowered or "public" in lowered:
                cat_name = "सार्वजनिक कार्यक्रम / Public Event"
            elif clean_text in {"EVENT_CAT_RELIGIOUS", "2"} or "धार्मिक" in lowered or "religious" in lowered:
                cat_name = "धार्मिक कार्यक्रम / Religious Event"
            elif clean_text in {"EVENT_CAT_WEDDING", "3"} or "लग्न" in lowered or "wedding" in lowered:
                cat_name = "लग्न समारंभ / Wedding"
            elif clean_text in {"EVENT_CAT_FESTIVAL", "4"} or "उत्सव" in lowered or "festival" in lowered:
                cat_name = "उत्सव / Festival"
            elif clean_text in {"EVENT_CAT_SCHOOL", "5"} or any(w in lowered for w in ["शाळा", "कॉलेज", "school", "college"]):
                cat_name = "कॉलेज किंवा शाळेचा कार्यक्रम / College or School Event"
            elif clean_text in {"EVENT_CAT_CLEANUP", "6"} or any(w in lowered for w in ["स्वच्छता", "clean-up", "cleanup"]):
                cat_name = "स्वच्छता अभियान / Clean-up Drive"
            elif clean_text in {"EVENT_CAT_OTHER", "7"} or "इतर" in lowered or "other" in lowered:
                cat_name = "इतर कार्यक्रम / Other Event"

            if cat_name:
                pending = json.loads(citizen.pending_complaint_data or "{}")
                pending["flow"] = "event"
                pending["category"] = cat_name
                citizen.conversation_state = "AWAITING_EVENT_DATE"
                citizen.pending_complaint_data = json.dumps(pending)
                db.commit()
                reply = strings["event_ask_date"]
                WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
                return {"status": "awaiting_event_date", "reply": reply, "category": cat_name}
            else:
                reply = strings["event_category_prompt"]
                cat_list = WhatsAppService.build_event_categories_interactive(lang)
                WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply, interactive=cat_list)
                return {"status": "awaiting_event_category", "reply": reply}

        if citizen.conversation_state == "AWAITING_EVENT_DATE":
            if message_type != "text" or not clean_text:
                reply = "⚠️ कृपया तारीख DD/MM/YYYY स्वरूपात पाठवा.\n\n" + strings["event_ask_date"]
                WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
                return {"status": "invalid_event_date", "reply": reply}

            ok, parsed_date, err = WhatsAppService.parse_and_validate_event_date(clean_text)
            if not ok:
                reply = f"⚠️ {err}\n\n" + strings["event_ask_date"]
                WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
                return {"status": "invalid_event_date", "reply": reply}

            pending = json.loads(citizen.pending_complaint_data or "{}")
            pending["event_date"] = parsed_date.strftime("%Y-%m-%d")
            pending["event_date_display"] = parsed_date.strftime("%d/%m/%Y")
            citizen.conversation_state = "AWAITING_EVENT_TIME"
            citizen.pending_complaint_data = json.dumps(pending)
            db.commit()
            reply = strings["event_ask_time"]
            WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
            return {"status": "awaiting_event_time", "reply": reply, "event_date": pending["event_date"]}

        if citizen.conversation_state == "AWAITING_EVENT_TIME":
            if message_type != "text" or not clean_text:
                reply = "⚠️ कृपया वेळ पाठवा (उदा. 06:30 PM किंवा 18:30).\n\n" + strings["event_ask_time"]
                WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
                return {"status": "invalid_event_time", "reply": reply}

            ok, parsed_time, err = WhatsAppService.parse_and_validate_event_time(clean_text)
            if not ok:
                reply = f"⚠️ {err}\n\n" + strings["event_ask_time"]
                WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
                return {"status": "invalid_event_time", "reply": reply}

            pending = json.loads(citizen.pending_complaint_data or "{}")
            pending["event_time"] = parsed_time
            citizen.conversation_state = "AWAITING_EVENT_LOCATION"
            citizen.pending_complaint_data = json.dumps(pending)
            db.commit()
            reply = strings["event_ask_location"]
            WhatsAppService.send_meta_location_request(citizen.phone_number, reply)
            return {"status": "awaiting_event_location", "reply": reply, "event_time": parsed_time}

        if citizen.conversation_state == "AWAITING_EVENT_LOCATION":
            loc_captured = False
            lat_val = None
            lng_val = None
            loc_addr = None

            if message_type == "location" or (latitude is not None and longitude is not None):
                try:
                    lat_val = float(latitude)
                    lng_val = float(longitude)
                    if math.isfinite(lat_val) and math.isfinite(lng_val) and -90 <= lat_val <= 90 and -180 <= lng_val <= 180:
                        loc_addr = f"Geotagged via WhatsApp ({lat_val:.6f}, {lng_val:.6f})"
                        loc_captured = True
                except (TypeError, ValueError):
                    pass

            elif clean_text.upper().startswith("ADDRESS:") or clean_text.startswith("पत्ता:"):
                manual_address = clean_text.split(":", 1)[1].strip()
                if manual_address:
                    loc_addr = manual_address
                    lat_val = None
                    lng_val = None
                    loc_captured = True
            elif len(clean_text) > 3 and not clean_text.isdigit():
                loc_addr = clean_text
                lat_val = None
                lng_val = None
                loc_captured = True

            if not loc_captured:
                reply = strings["event_ask_location"]
                WhatsAppService.send_meta_location_request(citizen.phone_number, reply)
                return {"status": "awaiting_event_location", "reply": reply}

            pending = json.loads(citizen.pending_complaint_data or "{}")
            pending["latitude"] = lat_val
            pending["longitude"] = lng_val
            pending["location_address"] = loc_addr
            citizen.conversation_state = "AWAITING_EVENT_CONFIRMATION"
            citizen.pending_complaint_data = json.dumps(pending)
            db.commit()

            summary_text = strings["event_summary"].format(
                category=pending.get("category", "Public Event"),
                date=pending.get("event_date_display") or pending.get("event_date"),
                time=pending.get("event_time"),
                location=loc_addr
            )
            confirm_buttons = [
                ("EVENT_CONFIRM", "✅ Confirm / खात्री"),
                ("EVENT_CANCEL", "❌ Cancel / रद्द")
            ]
            interactive = WhatsAppService.build_quick_buttons_interactive(summary_text, confirm_buttons)
            WhatsAppService.send_meta_whatsapp(citizen.phone_number, summary_text, interactive=interactive)
            return {"status": "awaiting_event_confirmation", "reply": summary_text}

        if citizen.conversation_state == "AWAITING_EVENT_CONFIRMATION":
            if clean_text in {"EVENT_CONFIRM", "1"} or lowered in {"confirm", "खात्री", "हो", "yes", "confirm event"}:
                if message_id:
                    existing_evt = db.query(EventReport).filter(EventReport.source_message_id == message_id).first()
                    if existing_evt:
                        logger.info("[WHATSAPP RETRY] Message ID '%s' already applied to EventReport #%s", message_id, existing_evt.reference_id)
                        reply = strings["event_success"].format(
                            ref_id=existing_evt.reference_id,
                            date=existing_evt.event_date.strftime("%d/%m/%Y"),
                            time=existing_evt.event_time,
                            location=existing_evt.location_address
                        )
                        WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
                        return {"status": "event_created", "reference_id": existing_evt.reference_id, "reply": reply, "recovered": True}

                pending = json.loads(citizen.pending_complaint_data or "{}")
                ref_id = _generate_event_reference_id()
                raw_date = pending.get("event_date", "")
                try:
                    parsed_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
                except (ValueError, TypeError):
                    try:
                        parsed_date = datetime.strptime(raw_date, "%d/%m/%Y").date()
                    except Exception:
                        parsed_date = datetime.now(timezone.utc).date()

                new_evt = EventReport(
                    reference_id=ref_id,
                    source_message_id=message_id,
                    citizen_id=citizen.user_id,
                    whatsapp_citizen_id=citizen.id,
                    category=pending.get("category", "सार्वजनिक कार्यक्रम / Public Event"),
                    event_date=parsed_date,
                    event_time=pending.get("event_time", "06:00 PM"),
                    location_address=(pending.get("location_address") or "Location not provided")[:512],
                    latitude=pending.get("latitude"),
                    longitude=pending.get("longitude"),
                    status="submitted"
                )
                db.add(new_evt)
                citizen.conversation_state = "IDLE"
                citizen.pending_complaint_data = None
                db.commit()

                reply = strings["event_success"].format(
                    ref_id=ref_id,
                    date=pending.get("event_date_display") or raw_date,
                    time=pending.get("event_time", "06:00 PM"),
                    location=new_evt.location_address
                )
                WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
                return {"status": "event_created", "reference_id": ref_id, "reply": reply}

            elif clean_text in {"EVENT_CANCEL", "2"} or lowered in {"cancel", "रद्द", "no", "नाही"}:
                citizen.conversation_state = "IDLE"
                citizen.pending_complaint_data = None
                db.commit()
                reply = strings["event_cancelled"]
                WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
                return {"status": "event_cancelled", "reply": reply}
            else:
                summary_text = "कृपया Confirm किंवा Cancel निवडा / Please tap Confirm or Cancel."
                confirm_buttons = [
                    ("EVENT_CONFIRM", "✅ Confirm / खात्री"),
                    ("EVENT_CANCEL", "❌ Cancel / रद्द")
                ]
                interactive = WhatsAppService.build_quick_buttons_interactive(summary_text, confirm_buttons)
                WhatsAppService.send_meta_whatsapp(citizen.phone_number, summary_text, interactive=interactive)
                return {"status": "awaiting_event_confirmation", "reply": summary_text}

        # ----------------------------------------------------------------
        # MANUAL ADDRESS FALLBACK IN AWAITING_LOCATION STATE
        # ----------------------------------------------------------------
        manual_waste_address = None
        if citizen.conversation_state == "AWAITING_LOCATION" and message_type == "text":
            if clean_text.upper().startswith("ADDRESS:") or clean_text.startswith("पत्ता:"):
                manual_waste_address = clean_text.split(":", 1)[1].strip()
                if not manual_waste_address:
                    reply = strings["ask_location"]
                    WhatsAppService.send_meta_location_request(citizen.phone_number, reply)
                    return {"status": "awaiting_location", "reply": reply}
            elif clean_text in {"1", "2", "3", "4", "5", "6", "7", "8", "9"} or is_menu_cmd:
                return _present_main_menu()
            else:
                # Text followup while waiting for location repeats prompt
                reply = strings["ask_location"]
                WhatsAppService.send_meta_location_request(citizen.phone_number, reply)
                return {"status": "awaiting_location", "reply": reply}

        # ----------------------------------------------------------------
        # STEP 2: Multi-Step Waste Reporting: Photo Ingestion
        # ----------------------------------------------------------------
        if message_type == "image" or "http" in media_url or media_id:
            if media_id:
                pending = json.loads(citizen.pending_complaint_data or "{}")
                if (
                    citizen.conversation_state == "AWAITING_LOCATION"
                    and pending.get("media_id") == media_id
                ):
                    reply = strings["ask_location"]
                    WhatsAppService.send_meta_location_request(citizen.phone_number, reply)
                    return {"status": "awaiting_location", "reply": reply, "image_url": pending["image_url"]}

                media_res = WhatsAppService.fetch_and_store_meta_media(media_id)
                if not media_res.get("success"):
                    if media_res.get("retryable"):
                        raise RetryableWhatsAppError("Meta image retrieval temporarily failed")
                    reply = strings.get("image_error")
                    WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
                    return {"status": "media_error", "reply": reply, "error": media_res.get("error")}

                stored_ref = media_res["storage_ref"]
                citizen.conversation_state = "AWAITING_LOCATION"
                citizen.pending_complaint_data = json.dumps({
                    "flow": "waste",
                    "image_url": stored_ref,
                    "media_id": media_id,
                    "mime_type": media_res.get("mime_type"),
                    "sha256": media_res.get("sha256"),
                    "file_size": media_res.get("file_size"),
                    "waste_type": "Mixed Municipal Waste"
                })
                db.commit()

                photo_ack = strings.get("photo_received_ack", "📸 Photo received! / फोटो प्राप्त झाला! ✅")
                WhatsAppService.send_meta_whatsapp(citizen.phone_number, photo_ack)

                reply = strings["ask_location"]
                WhatsAppService.send_meta_location_request(citizen.phone_number, reply)
                return {"status": "awaiting_location", "reply": reply, "image_url": stored_ref}

            elif media_url:
                citizen.conversation_state = "AWAITING_LOCATION"
                citizen.pending_complaint_data = json.dumps({
                    "flow": "waste",
                    "image_url": media_url,
                    "waste_type": "Mixed Municipal Waste"
                })
                db.commit()

                photo_ack = strings.get("photo_received_ack", "📸 Photo received! / फोटो प्राप्त झाला! ✅")
                WhatsAppService.send_meta_whatsapp(citizen.phone_number, photo_ack)

                reply = strings["ask_location"]
                WhatsAppService.send_meta_location_request(citizen.phone_number, reply)
                return {"status": "awaiting_location", "reply": reply, "image_url": media_url}

        # ----------------------------------------------------------------
        # STEP 3: Multi-Step Waste Reporting: Location Pin or Manual Address Fallback
        # ----------------------------------------------------------------
        is_location_event = (message_type == "location") or (latitude is not None and longitude is not None)
        if is_location_event or manual_waste_address:
            # Idempotency / Retry recovery
            if message_id:
                from server.models.whatsapp_session import WhatsAppProcessedMessage
                proc_msg = db.query(WhatsAppProcessedMessage).filter(
                    WhatsAppProcessedMessage.message_id == message_id
                ).first()
                if proc_msg and proc_msg.complaint_id:
                    existing_complaint = db.query(Complaint).filter(
                        Complaint.id == proc_msg.complaint_id
                    ).first()
                    if existing_complaint:
                        logger.info(
                            f"[WHATSAPP RETRY] Message ID '{message_id}' already applied to complaint "
                            f"#{existing_complaint.tracking_number} (ID: {existing_complaint.id}); recovering original confirmation."
                        )
                        reply = strings["report_success"].format(
                            ticket=existing_complaint.tracking_number,
                            location=existing_complaint.location_address or "Dhule",
                            driver=existing_complaint.assigned_driver_name or (
                                "लवकरच नियुक्त केला जाईल" if lang == "mr" else "Pending Assignment"
                            ),
                            coins=citizen.eco_coins
                        )
                        WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
                        return {
                            "status": "complaint_created",
                            "ticket": existing_complaint.tracking_number,
                            "reply": reply,
                            "recovered": True
                        }

            if citizen.conversation_state != "AWAITING_LOCATION":
                pending_raw = citizen.pending_complaint_data
                pending = json.loads(pending_raw) if pending_raw else {}
                image_url = pending.get("image_url")
                if not image_url:
                    citizen.conversation_state = "AWAITING_PHOTO"
                    db.commit()
                    reply = strings["ask_photo"]
                    WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
                    return {"status": "awaiting_photo", "reply": reply}
                else:
                    reply = "📍 सध्या कोणतेही लोकेशन अपेक्षित नाही. / No active location request.\n\n" + strings["menu_options"]
                    WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
                    return {"status": "unexpected_location", "reply": reply}

            lat_val = None
            lng_val = None
            if is_location_event:
                try:
                    lat_val = float(latitude)
                    lng_val = float(longitude)
                    valid_location = (
                        math.isfinite(lat_val)
                        and math.isfinite(lng_val)
                        and -90 <= lat_val <= 90
                        and -180 <= lng_val <= 180
                    )
                except (TypeError, ValueError):
                    valid_location = False

                if not valid_location:
                    reply = strings["invalid_location"]
                    WhatsAppService.send_meta_location_request(citizen.phone_number, reply)
                    return {"status": "invalid_location", "reply": reply}

            pending_raw = citizen.pending_complaint_data
            pending = json.loads(pending_raw) if pending_raw else {}
            image_url = pending.get("image_url")

            if not image_url:
                citizen.conversation_state = "AWAITING_PHOTO"
                db.commit()
                reply = strings["ask_photo"]
                WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
                return {"status": "awaiting_photo", "reply": reply}

            waste_type = pending.get("waste_type", "Garbage Overflow")

            citizen_user = None
            if citizen.user_id:
                citizen_user = db.query(User).filter(User.id == citizen.user_id).first()
            if not citizen_user:
                citizen_user = WhatsAppService.find_matching_citizen_user(db, citizen.phone_number)
            citizen_user_id = citizen_user.id if citizen_user else None

            assigned_driver = WhatsAppService.select_eligible_driver(db)
            if assigned_driver:
                assigned_driver_id = assigned_driver.id
                assigned_driver_name = (
                    f"{assigned_driver.full_name} ({assigned_driver.employee_id})"
                    if assigned_driver.employee_id
                    else assigned_driver.full_name
                )
                driver_display = assigned_driver_name
            else:
                assigned_driver_id = None
                assigned_driver_name = None
                driver_display = "लवकरच नियुक्त केला जाईल" if lang == "mr" else "Pending Assignment"

            if manual_waste_address:
                location_address = manual_waste_address
                lat_val = None
                lng_val = None
            else:
                location_address = f"Geotagged via WhatsApp ({lat_val:.4f}, {lng_val:.4f}), Dhule"
                if citizen.ward:
                    location_address = f"{citizen.ward}, {location_address}"

            new_complaint = None
            ticket_num = None
            _coins_before = citizen.eco_coins
            _state_before = citizen.conversation_state
            _pending_before = citizen.pending_complaint_data
            for _attempt in range(_WA_MAX_RETRIES):
                ticket_num = _generate_whatsapp_tracking_id(citizen.ward or "0")
                try:
                    household_tag = f" {citizen.household_id}" if citizen.household_id else ""
                    description = f"Reported via WhatsApp by linked citizen{household_tag} (EcoPulse AI — Dhule)."
                    new_complaint = Complaint(
                        tracking_number=ticket_num,
                        citizen_id=citizen_user_id,
                        whatsapp_citizen_id=citizen.id,
                        ward=citizen.ward or "Dhule Ward 1",
                        location_address=location_address,
                        latitude=lat_val,
                        longitude=lng_val,
                        waste_type=waste_type,
                        description=description,
                        image_url=image_url,
                        ai_status="Verified",
                        ai_confidence=0.96,
                        status="Pending",
                        assigned_driver_id=assigned_driver_id,
                        assigned_driver_name=assigned_driver_name
                    )
                    db.add(new_complaint)
                    db.flush()

                    new_task = DriverTask(
                        driver_id=assigned_driver_id,
                        complaint_id=new_complaint.id,
                        location_name=new_complaint.location_address,
                        status="Pending",
                        route_order=1
                    )
                    db.add(new_task)

                    citizen.eco_coins = _coins_before + 20
                    if citizen_user:
                        citizen_user.eco_coins = (citizen_user.eco_coins or 100) + 20
                    citizen.conversation_state = "IDLE"
                    citizen.pending_complaint_data = None

                    if message_id:
                        from server.models.whatsapp_session import WhatsAppProcessedMessage
                        db.query(WhatsAppProcessedMessage).filter(
                            WhatsAppProcessedMessage.message_id == message_id
                        ).update({
                            "complaint_id": new_complaint.id
                        })

                    db.commit()
                    break

                except Exception as exc:
                    db.rollback()
                    citizen.eco_coins = _coins_before
                    citizen.conversation_state = _state_before
                    citizen.pending_complaint_data = _pending_before

                    if _is_tracking_number_collision(exc):
                        if _attempt < _WA_MAX_RETRIES - 1:
                            continue
                        raise RuntimeError("Could not generate unique tracking number.") from exc
                    raise

            reply = strings["complaint_created"].format(
                ticket=ticket_num,
                type=waste_type,
                driver=driver_display
            )
            report_buttons = [
                ("MENU_MY_COMPLAINTS", "माझ्या तक्रारी" if lang == "mr" else "My Complaints"),
                ("MENU_MAIN", "मुख्य मेनू" if lang == "mr" else "Main Menu")
            ]
            interactive = WhatsAppService.build_quick_buttons_interactive(reply, report_buttons)
            WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply, interactive=interactive)
            return {"status": "complaint_created", "ticket": ticket_num, "reply": reply}

        # ----------------------------------------------------------------
        # Handle AWAITING_GENERAL_COMPLAINT state
        # ----------------------------------------------------------------
        if citizen.conversation_state == "AWAITING_GENERAL_COMPLAINT" and clean_text:
            citizen_user_id = citizen.user_id
            assigned_driver = WhatsAppService.select_eligible_driver(db)
            if assigned_driver:
                assigned_driver_id = assigned_driver.id
                assigned_driver_name = (
                    f"{assigned_driver.full_name} ({assigned_driver.employee_id})"
                    if assigned_driver.employee_id
                    else assigned_driver.full_name
                )
                driver_display = assigned_driver_name
            else:
                assigned_driver_id = None
                assigned_driver_name = None
                driver_display = "लवकरच नियुक्त केला जाईल" if lang == "mr" else "Pending Assignment"

            _coins_before = citizen.eco_coins
            _state_before = citizen.conversation_state
            for _attempt in range(_WA_MAX_RETRIES):
                ticket_num = _generate_whatsapp_tracking_id(citizen.ward or "0")
                try:
                    new_complaint = Complaint(
                        tracking_number=ticket_num,
                        citizen_id=citizen_user_id,
                        whatsapp_citizen_id=citizen.id,
                        ward=citizen.ward or "Dhule Ward 1",
                        location_address="Dhule (reported via WhatsApp text)",
                        waste_type="General Complaint",
                        description=clean_text[:500],
                        ai_status="Pending Review",
                        ai_confidence=0.0,
                        status="Pending",
                        assigned_driver_id=assigned_driver_id,
                        assigned_driver_name=assigned_driver_name
                    )
                    db.add(new_complaint)
                    db.flush()

                    new_task = DriverTask(
                        driver_id=assigned_driver_id,
                        complaint_id=new_complaint.id,
                        location_name=new_complaint.location_address,
                        status="Pending",
                        route_order=1
                    )
                    db.add(new_task)

                    citizen.eco_coins = _coins_before + 10
                    citizen.conversation_state = "IDLE"
                    db.commit()
                    break
                except Exception as exc:
                    db.rollback()
                    citizen.eco_coins = _coins_before
                    citizen.conversation_state = _state_before
                    if _is_tracking_number_collision(exc):
                        if _attempt < _WA_MAX_RETRIES - 1:
                            continue
                        raise RuntimeError("Could not generate unique tracking number.") from exc
                    raise

            reply = strings["general_complaint_received"].format(
                ticket=ticket_num,
                description=clean_text[:100] + ("..." if len(clean_text) > 100 else ""),
                driver=driver_display
            )
            gen_buttons = [
                ("MENU_MY_COMPLAINTS", "माझ्या तक्रारी" if lang == "mr" else "My Complaints"),
                ("MENU_MAIN", "मुख्य मेनू" if lang == "mr" else "Main Menu")
            ]
            interactive = WhatsAppService.build_quick_buttons_interactive(reply, gen_buttons)
            WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply, interactive=interactive)
            return {"status": "awaiting_general_complaint", "ticket": ticket_num, "reply": reply}

        # ----------------------------------------------------------------
        # 8-OPTION MAIN MENU DISPATCH
        # ----------------------------------------------------------------
        # Option 1: Waste Complaint
        if clean_text in {"MENU_REPORT_WASTE", "1"} or "कचरा" in lowered or "waste" in lowered or "report" in lowered or "तक्रार नोंद" in lowered:
            citizen.conversation_state = "AWAITING_PHOTO"
            db.commit()
            reply = strings["ask_photo"]
            btn = [("MENU_MAIN", "मुख्य मेनू" if lang == "mr" else "Main Menu")]
            interactive = WhatsAppService.build_quick_buttons_interactive(reply, btn)
            WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply, interactive=interactive)
            return {"status": "awaiting_photo", "reply": reply}

        # Option 2: General Complaint
        if clean_text in {"MENU_GENERAL_COMPLAINT", "2"} or "सामान्य" in lowered or "general" in lowered:
            citizen.conversation_state = "AWAITING_GENERAL_COMPLAINT"
            db.commit()
            reply = strings["general_complaint_prompt"]
            btn = [("MENU_MAIN", "मुख्य मेनू" if lang == "mr" else "Main Menu")]
            interactive = WhatsAppService.build_quick_buttons_interactive(reply, btn)
            WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply, interactive=interactive)
            return {"status": "awaiting_general_complaint", "reply": reply}

        # Option 3: Live Truck Tracking
        if clean_text in {"MENU_VEHICLE_TRACKING", "3"} or "गाडी" in lowered or "घंटागाडी" in lowered or "truck" in lowered or "vehicle" in lowered or "track" in lowered:
            reply = strings["truck_unavailable"]
            btn = [("MENU_MAIN", "मुख्य मेनू" if lang == "mr" else "Main Menu")]
            interactive = WhatsAppService.build_quick_buttons_interactive(reply, btn)
            WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply, interactive=interactive)
            return {"status": "truck_unavailable", "reply": reply}

        # Option 4: Waste Collection Schedule
        if clean_text in {"MENU_COLLECTION_SCHEDULE", "4"} or "वेळापत्रक" in lowered or "schedule" in lowered or "टाइम" in lowered:
            reply = strings["schedule_unavailable"]
            btn = [("MENU_MAIN", "मुख्य मेनू" if lang == "mr" else "Main Menu")]
            interactive = WhatsAppService.build_quick_buttons_interactive(reply, btn)
            WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply, interactive=interactive)
            return {"status": "schedule_unavailable", "reply": reply}

        # Option 5: Eco Wallet & Rewards
        if clean_text in {"MENU_ECO_WALLET", "5"} or "wallet" in lowered or "coin" in lowered or "वॉलेट" in lowered:
            reply = strings["wallet_info"].format(
                coins=citizen.eco_coins,
                rupees=citizen.eco_coins // 2
            )
            btn = [("MENU_MAIN", "मुख्य मेनू" if lang == "mr" else "Main Menu")]
            interactive = WhatsAppService.build_quick_buttons_interactive(reply, btn)
            WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply, interactive=interactive)
            return {"status": "wallet_info", "reply": reply}

        # Option 6: My Complaints Status
        if clean_text in {"MENU_MY_COMPLAINTS", "6"} or "तक्रारी" in lowered or "my complaints" in lowered or "status" in lowered or "माझ्या तक्रारी" in lowered:
            complaints_query = db.query(Complaint).filter(
                or_(
                    Complaint.whatsapp_citizen_id == citizen.id,
                    Complaint.citizen_id == citizen.user_id if citizen.user_id else False
                )
            ).order_by(Complaint.created_at.desc()).limit(3)
            user_complaints = complaints_query.all()

            if not user_complaints:
                reply = strings["no_complaints"]
            else:
                reply = strings["complaints_header"]
                for c in user_complaints:
                    status_emoji = "⏳" if c.status == "Pending" else ("🚚" if c.status == "In Progress" else "✅")
                    date_str = c.created_at.strftime("%d/%m/%Y") if c.created_at else "Today"
                    reply += f"{status_emoji} *#{c.tracking_number}* ({date_str})\n"
                    reply += f"   प्रकार / Type: {c.waste_type}\n"
                    reply += f"   स्थिती / Status: *{c.status}*\n"
                    if c.assigned_driver_name:
                        reply += f"   गाडी / Vehicle: {c.assigned_driver_name}\n"
                    reply += "\n"

            btn = [
                ("MENU_REPORT_WASTE", "नवीन तक्रार" if lang == "mr" else "New Complaint"),
                ("MENU_MAIN", "मुख्य मेनू" if lang == "mr" else "Main Menu")
            ]
            interactive = WhatsAppService.build_quick_buttons_interactive(reply, btn)
            WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply, interactive=interactive)
            return {"status": "track_complaints", "reply": reply}

        # Option 7: Municipal Notices (Leaderboard completely removed)
        if clean_text in {"MENU_NOTICES", "7"} or "notice" in lowered or "सूचना" in lowered:
            reply = strings["notices_unavailable"]
            btn = [("MENU_MAIN", "मुख्य मेनू" if lang == "mr" else "Main Menu")]
            interactive = WhatsAppService.build_quick_buttons_interactive(reply, btn)
            WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply, interactive=interactive)
            return {"status": "notices_unavailable", "reply": reply}

        # Direct Language Switch
        if clean_text == "LANG_EN" or (clean_text not in {"8", "9"} and lowered == "english"):
            new_lang = "en"
            citizen.preferred_language = new_lang
            db.commit()
            all_texts = _build_texts()
            strings = all_texts["en"]
            reply = "Language changed to English 🇬🇧\n\n" + strings["help_text"]
            btn = [("MENU_MAIN", "Main Menu")]
            interactive = WhatsAppService.build_quick_buttons_interactive(reply, btn)
            WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply, interactive=interactive)
            return {"status": "help", "reply": reply}

        if clean_text == "LANG_MR" or (clean_text not in {"8", "9"} and lowered in {"marathi", "मराठी"}):
            new_lang = "mr"
            citizen.preferred_language = new_lang
            db.commit()
            all_texts = _build_texts()
            strings = all_texts["mr"]
            reply = "भाषा मराठी म्हणून सेट केली आहे 🇮🇳\n\n" + strings["help_text"]
            btn = [("MENU_MAIN", "मुख्य मेनू")]
            interactive = WhatsAppService.build_quick_buttons_interactive(reply, btn)
            WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply, interactive=interactive)
            return {"status": "help", "reply": reply}

        # Option 8 / Option 9: Help & Language
        if clean_text in {"MENU_HELP_LANG", "8", "9"} or "help" in lowered or "मदत" in lowered or "भाषा" in lowered:
            reply = strings["help_text"]
            help_buttons = [
                ("LANG_EN", "English"),
                ("LANG_MR", "मराठी"),
                ("MENU_MAIN", "मुख्य मेनू" if lang == "mr" else "Main Menu")
            ]
            interactive = WhatsAppService.build_quick_buttons_interactive(reply, help_buttons)
            WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply, interactive=interactive)
            return {"status": "help", "reply": reply}

        # Public Event Reporting Keyword Entry Point
        if clean_text in {"MENU_REPORT_EVENT", "EVENT", "EVENT_REPORT"} or "event" in lowered or "कार्यक्रम" in lowered or "समारंभ" in lowered or "इव्हेंट" in lowered:
            citizen.conversation_state = "AWAITING_EVENT_CATEGORY"
            citizen.pending_complaint_data = json.dumps({"flow": "event"})
            db.commit()
            reply = strings["event_category_prompt"]
            cat_list = WhatsAppService.build_event_categories_interactive(lang)
            WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply, interactive=cat_list)
            return {"status": "awaiting_event_category", "reply": reply}

        # Unrecognized message fallback: present menu with helpful feedback
        extra = "⚠️ Unrecognized option / पर्याय उपलब्ध नाही."
        return _present_main_menu(extra_note=extra)
