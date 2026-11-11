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
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_
from server.utils.config import config
from server.models.whatsapp_session import WhatsAppCitizen
from server.models.complaint import Complaint
from server.models.task import DriverTask
from server.models.user import User
from server.services.media_storage import get_media_storage
from server.services.complaint_service import _is_tracking_number_collision

logger = logging.getLogger(__name__)

# Shared alphabet for tracking IDs: uppercase alphanumeric minus ambiguous I and O.
_ID_ALPHABET = (string.ascii_uppercase + string.digits).translate(
    str.maketrans("", "", "IO")
)
_ID_SUFFIX_LEN = 9
_WA_MAX_RETRIES = 5


def _generate_whatsapp_tracking_id(ward: str) -> str:
    """Generate a collision-resistant WhatsApp complaint tracking number.

    Format: <PREFIX>2026-W<ward_number>-<9 uppercase alphanumeric chars>
    Example: DHL-2026-W12-A7BZ3XKQR
    Total length: ≤ 28 chars — fits String(30).
    """
    prefix = getattr(config, "TRACKING_PREFIX", "DHL-").rstrip("-") + "-"
    ward_num = ward.replace("Ward ", "").strip() if ward else "0"
    suffix = "".join(secrets.choice(_ID_ALPHABET) for _ in range(_ID_SUFFIX_LEN))
    return f"{prefix}2026-W{ward_num}-{suffix}"


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
                "1️⃣ *कचरा तक्रार नोंदवा* — Report Waste\n"
                "2️⃣ *सामान्य तक्रार* — General Complaint\n"
                "3️⃣ *घंटागाडी ट्रॅकिंग* — Garbage Vehicle Tracking\n"
                "4️⃣ *संकलन वेळापत्रक* — Collection Schedule\n"
                "5️⃣ *ईको-वॉलेट आणि रिवॉर्ड्स* — Eco-Wallet & Rewards\n"
                "6️⃣ *माझ्या तक्रारी* — My Complaints\n"
                "7️⃣ *लीडरबोर्ड* — Leaderboard\n"
                "8️⃣ *महानगरपालिका सूचना* — Municipal Notices\n"
                "9️⃣ *मदत / भाषा बदला* — Help / Change Language\n\n"
                "👉 *पर्याय क्रमांक (1-9) पाठवा किंवा थेट फोटो पाठवा.*"
            ),
            "ask_photo": (
                "📸 *कचरा तक्रार नोंदणी*\n\n"
                "कृपया कचऱ्याचा, घाणीचा किंवा ओव्हरफ्लो झालेल्या कुंडीचा *फोटो पाठवा*."
            ),
            "ask_location": (
                "📍 *फोटो प्राप्त झाला!*\n\n"
                "आता कृपया खालील अटॅचमेंट चिन्हावर क्लिक करून *WhatsApp Location (आपले सध्याचे स्थान)* पाठवा."
            ),
            "invalid_location": (
                "⚠️ वैध स्थान मिळाले नाही. कृपया अटॅचमेंट (+) मधून आपले सध्याचे WhatsApp Location पुन्हा पाठवा."
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
            "general_complaint_prompt": (
                "📝 *सामान्य तक्रार*\n\n"
                "कृपया आपली तक्रार थोडक्यात लिहा (रस्ता, पाणी, दिवे, अतिक्रमण इ.).\n"
                "उदा: *मेन रोडवर मोठा खड्डा आहे, दुरुस्ती आवश्यक आहे.*"
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
            "leaderboard_unavailable": (
                "🏆 *ईको लीडरबोर्ड*\n\n"
                "⚠️ लीडरबोर्ड लवकरच उपलब्ध होणार आहे.\n"
                "सध्या आपले ईको-कॉइन्स: *{coins} गुण*\n\n"
                "अधिक तक्रारी नोंदवा आणि शहर स्वच्छ ठेवण्यात सहभागी व्हा! 🌱"
            ),
            "notices_unavailable": (
                "📢 *धुळे महानगरपालिका सूचना*\n\n"
                "⚠️ सध्या कोणतीही नवीन अधिकृत सूचना नाही.\n"
                "अद्ययावत माहितीसाठी: https://dmc.gov.in\n\n"
                "📞 धुळे महानगरपालिका: 0562-XXXXXX"
            ),
            "help_text": (
                "ℹ️ *EcoPulse AI — मदत*\n\n"
                "📌 *उपलब्ध आदेश:*\n"
                "• *LINK <code>* — वेबसाइट खाते जोडा\n"
                "• *1 ते 9* — मेनू पर्याय निवडा\n"
                "• फोटो पाठवा — थेट कचरा तक्रार\n\n"
                f"🌐 *वेबसाइट:* {frontend_url}\n"
                "📞 *हेल्पलाइन:* 0562-XXXXXX\n\n"
                "भाषा बदलण्यासाठी: *9* पाठवा आणि 'English' लिहा."
            ),
            "image_error": (
                "⚠️ *फोटो स्वीकारला नाही.*\n\n"
                "कृपया स्पष्ट JPEG, PNG किंवा WebP स्वरूपातील फोटो पाठवा (कमाल १० MB)."
            ),
            "link_success": (
                "✅ *WhatsApp खाते यशस्वीरित्या जोडले!*\n\n"
                "आपण आता EcoPulse AI सेवा वापरू शकता."
            ),
            "link_invalid": (
                "❌ *कोड अवैध किंवा कालबाह्य झाला.*\n\n"
                "कृपया EcoPulse वेबसाइटवर पुन्हा लॉगिन करा आणि नवीन कोड मिळवा:\n"
                f"🌐 {frontend_url}"
            ),
            "lang_switched": "✅ भाषा बदलून मराठी करण्यात आली आहे.",
            "general_complaint_received": (
                "✅ *सामान्य तक्रार प्राप्त झाली!*\n\n"
                "🎫 *तक्रार क्र.:* #{ticket}\n"
                "📋 *तक्रार:* {description}\n"
                "🚛 *नियुक्त:* {driver}\n\n"
                "आमची टीम लवकरच संपर्क करेल."
            ),
        },
        "en": {
            "unauthorized": onboarding_en,
            "not_linked_prompt": onboarding_en,
            "linked_welcome": (
                "✅ *Dhule EcoPulse AI — Account Linked Successfully!*\n\n"
                "Welcome {name}! 🎉\n"
                "Your WhatsApp number has been linked to your EcoPulse account.\n\n"
                "🪙 *EcoCoin Balance: {coins} pts*\n\n"
                "Please choose an option below:"
            ),
            "authorized_welcome": (
                f"🏛️ *EcoPulse AI — {muni_en}*\n\n"
                "Welcome back {name}! 👋\n"
                "✅ Your EcoPulse account is active.\n\n"
                "🪙 *EcoCoin Balance: {coins} pts (₹{rupees} rebate)*\n\n"
                "Please choose an option below:"
            ),
            "menu_options": (
                "1️⃣ *Report Waste* — कचरा तक्रार नोंदवा\n"
                "2️⃣ *General Complaint* — सामान्य तक्रार\n"
                "3️⃣ *Garbage Vehicle Tracking* — घंटागाडी ट्रॅकिंग\n"
                "4️⃣ *Collection Schedule* — संकलन वेळापत्रक\n"
                "5️⃣ *Eco-Wallet & Rewards* — ईको-वॉलेट आणि रिवॉर्ड्स\n"
                "6️⃣ *My Complaints* — माझ्या तक्रारी\n"
                "7️⃣ *Leaderboard* — लीडरबोर्ड\n"
                "8️⃣ *Municipal Notices* — महानगरपालिका सूचना\n"
                "9️⃣ *Help / Change Language* — मदत / भाषा बदला\n\n"
                "👉 *Reply with number (1-9) or send a photo directly.*"
            ),
            "ask_photo": (
                "📸 *Report Waste Incident*\n\n"
                "Please capture and *send a photo* of the garbage accumulation or overflowing bin."
            ),
            "ask_location": (
                "📍 *Photo Received!*\n\n"
                "Now click the (+) attachment icon and share your *WhatsApp Location*."
            ),
            "invalid_location": (
                "⚠️ I couldn't read a valid location. Please share your current WhatsApp location pin "
                "using the attachment (+) menu."
            ),
            "report_success": (
                "✅ *Complaint Logged Successfully!*\n\n"
                "🎫 *Ticket ID:* #{ticket}\n"
                "📍 *Location:* {location}\n"
                "🚛 *Assigned Vehicle:* {driver}\n"
                "⏱️ *Resolution SLA:* Within 4 hours\n\n"
                "🎉 *Reward:* You earned *+20 EcoCoins* for keeping Dhule clean!\n"
                "Total Balance: *{coins} pts*."
            ),
            "general_complaint_prompt": (
                "📝 *General Complaint*\n\n"
                "Please briefly describe the civic sanitation issue (road, water, streetlight, encroachment etc.).\n"
                "Example: *Large pothole near main road, requires immediate repair.*"
            ),
            "no_complaints": (
                "🔍 No active complaints found for your account. All clear! 🌟"
            ),
            "complaints_header": "🔍 *Your Active Complaints:*\n\n",
            "wallet_info": (
                "🪙 *Dhule Municipal Eco-Wallet*\n\n"
                "Balance: *{coins} EcoCoins*\n"
                "Estimated Value: *₹{rupees}*\n\n"
                "🎁 *Redemption Options:*\n"
                "• 50 coins = ₹25 Municipal Property Tax Rebate\n"
                "• 100 coins = 1-Month Dhule Public Library Pass\n"
                "• 200 coins = 2 Free Saplings (Dhule Municipal Nursery)\n\n"
                "Contact Dhule Municipal Tax Department to claim."
            ),
            "truck_unavailable": (
                "🚛 *Garbage Truck Live GPS Tracking*\n\n"
                "⚠️ Live GPS tracking is currently not enabled for your sector.\n"
                "Please contact your ward sanitation supervisor or try again later.\n\n"
                "📞 Dhule Municipal Helpline: 0562-XXXXXX"
            ),
            "schedule_unavailable": (
                "🗓️ *Waste Collection Schedule*\n\n"
                "⚠️ Digital schedule for your area is not yet published.\n"
                "Morning collection: 7:00 AM - 11:00 AM daily.\n\n"
                "📞 Dhule Municipal: 0562-XXXXXX"
            ),
            "leaderboard_unavailable": (
                "🏆 *Eco Leaderboard*\n\n"
                "⚠️ Leaderboard is coming soon!\n"
                "Your current EcoCoins: *{coins} pts*\n\n"
                "Report more complaints and help keep Dhule clean! 🌱"
            ),
            "notices_unavailable": (
                "📢 *Dhule Municipal Corporation Notices*\n\n"
                "⚠️ No new official notices at this time.\n"
                "For updates visit: https://dmc.gov.in\n\n"
                "📞 Dhule Municipal: 0562-XXXXXX"
            ),
            "help_text": (
                "ℹ️ *EcoPulse AI — Help*\n\n"
                "📌 *Available commands:*\n"
                "• *LINK <code>* — Link your website account\n"
                "• *1 to 9* — Select menu option\n"
                "• Send a photo — Report waste directly\n\n"
                f"🌐 *Website:* {frontend_url}\n"
                "📞 *Helpline:* 0562-XXXXXX\n\n"
                "To switch language: send *9* then type 'Marathi'."
            ),
            "image_error": (
                "⚠️ *Could not process photo.*\n\n"
                "Please send a clear photo in JPEG, PNG, or WebP format (max 10 MB)."
            ),
            "link_success": (
                "✅ *WhatsApp account linked successfully!*\n\n"
                "You can now use all EcoPulse AI services."
            ),
            "link_invalid": (
                "❌ *Invalid or expired code.*\n\n"
                "Please log in to the EcoPulse website and generate a new code:\n"
                f"🌐 {frontend_url}"
            ),
            "lang_switched": "✅ Language switched to English.",
            "general_complaint_received": (
                "✅ *General Complaint Received!*\n\n"
                "🎫 *Ticket ID:* #{ticket}\n"
                "📋 *Complaint:* {description}\n"
                "🚛 *Assigned:* {driver}\n\n"
                "Our team will follow up shortly."
            ),
        }
    }

TEXTS = _build_texts()


class WhatsAppService:

    @staticmethod
    def normalize_phone(phone: str) -> str:
        """Normalize phone numbers by removing spaces, dashes, and leading plus."""
        if not phone:
            return ""
        cleaned = re.sub(r'[^0-9]', '', str(phone))
        # Ensure 10-digit Indian numbers get country code 91
        if len(cleaned) == 10:
            cleaned = '91' + cleaned
        return cleaned

    @staticmethod
    def get_or_create_citizen(db: Session, phone: str) -> WhatsAppCitizen:
        normalized = WhatsAppService.normalize_phone(phone)
        citizen = db.query(WhatsAppCitizen).filter(WhatsAppCitizen.phone_number == normalized).first()
        if not citizen:
            citizen = WhatsAppCitizen(
                phone_number=normalized,
                full_name="Dhule Citizen",
                ward=None,
                household_id=None,
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

        matches = db.query(User).filter(
            User.phone.in_(candidate_phones),
            User.role == "citizen",
            User.is_active == True
        ).all()

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
        eligible_drivers = db.query(User).filter(
            User.role == "driver",
            User.is_active == True,
            User.is_locked == False
        ).all()

        if not eligible_drivers:
            logger.info("[DRIVER ASSIGNMENT] No active registered drivers found; leaving complaint unassigned.")
            return None

        # Calculate active workload for each eligible driver
        driver_workloads = []
        for d in eligible_drivers:
            # Strictly ensure driver role
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
    def send_meta_whatsapp(to_phone: str, message_text: str, buttons: list = None) -> dict:
        """Send message via official Meta WhatsApp Business Cloud API."""
        token = config.WHATSAPP_TOKEN
        phone_id = config.WHATSAPP_PHONE_NUMBER_ID
        api_version = config.WHATSAPP_GRAPH_API_VERSION or "v20.0"

        if not token or not phone_id:
            logger.info("[MOCK META WHATSAPP] Outbound message simulated; provider credentials are not configured.")
            return {"status": "simulated"}

        url = f"https://graph.facebook.com/{api_version}/{phone_id}/messages"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

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
                # Step 1: Request metadata from Meta Graph API
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

                # Step 2: Download raw binary from returned download URL using Bearer token
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

            # Step 3: Server-side validation of media content & magic numbers
            detected_mime, ext = validate_image_content(content, declared_mime_type=declared_mime)

            # Step 4: Calculate SHA-256 integrity hash
            calc_sha256 = hashlib.sha256(content).hexdigest()

            # Step 5: Persist via storage abstraction
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
        """Central message handling engine for WhatsApp."""
        citizen = WhatsAppService.get_or_create_citizen(db, sender_phone)
        normalized_phone = WhatsAppService.normalize_phone(sender_phone)
        lang = citizen.preferred_language or "mr"
        all_texts = _build_texts()
        strings = all_texts.get(lang, all_texts["mr"])
        clean_text = (text_body or "").strip()
        media_url = (media_url or "").strip()

        # ----------------------------------------------------------------
        # STEP 0a: Detect VERIFY <code> command — Website Registration Verification
        # Processed BEFORE auth gatekeeper so registering citizens can verify mobile.
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
        # STEP 0: Detect LINK <code> command — processed BEFORE auth gatekeeper.
        # This allows unlinked senders to link their account.
        # ----------------------------------------------------------------
        link_match = re.match(r'^LINK(?:\s+(.*))?$', clean_text, re.IGNORECASE)
        if link_match:
            raw_code = (link_match.group(1) or "").strip()
            if not raw_code:
                reply = strings["link_invalid"]
                WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
                return {"status": "link_failed", "reply": reply}

            # Import here to avoid circular dependency
            from server.services.whatsapp_link_service import WhatsAppLinkService
            linked_user = WhatsAppLinkService.redeem_link_code(db, raw_code, normalized_phone)
            if linked_user:
                # Refresh citizen from DB (user_id FK is now populated)
                db.refresh(citizen)
                reply = strings["linked_welcome"].format(
                    name=linked_user.full_name or linked_user.email,
                    coins=citizen.eco_coins
                ) + "\n\n" + strings["menu_options"]
                WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
                return {"status": "linked", "citizen": citizen.phone_number, "reply": reply}
            else:
                reply = strings["link_invalid"]
                WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
                return {"status": "link_failed", "reply": reply}

        # ----------------------------------------------------------------
        # STEP 0b: Legacy QR code authorization support (backward compatibility)
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
        # STEP 1: Auth gatekeeper — citizen must have user_id (linked account)
        # ----------------------------------------------------------------
        is_linked = bool(citizen.user_id or citizen.is_authorized)
        if not is_linked:
            reply = strings["not_linked_prompt"]
            WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
            return {"status": "not_linked", "reply": reply}

        # Greeting handler for linked citizens
        lowered = clean_text.lower()
        if lowered in {"hey", "hello", "hi", "namaskar", "namaste", "नमस्कार", "start", "menu"}:
            citizen_name = "Citizen"
            if citizen.user_id:
                user_obj = db.query(User).filter(User.id == citizen.user_id).first()
                if user_obj and user_obj.full_name:
                    citizen_name = user_obj.full_name
            elif citizen.full_name and citizen.full_name != "Shirpur Resident":
                citizen_name = citizen.full_name

            reply = strings["authorized_welcome"].format(
                name=citizen_name,
                coins=citizen.eco_coins,
                rupees=citizen.eco_coins // 2
            ) + "\n\n" + strings["menu_options"]
            WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
            return {"status": "menu_presented", "reply": reply}

        if citizen.conversation_state == "AWAITING_LOCATION" and message_type == "text":
            reply = strings["ask_location"]
            WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
            return {"status": "awaiting_location", "reply": reply}

        # ----------------------------------------------------------------
        # STEP 2: Multi-Step Reporting State Machine: Photo Ingestion
        # ----------------------------------------------------------------
        if message_type == "image" or "http" in media_url or media_id:
            if media_id:
                pending = json.loads(citizen.pending_complaint_data or "{}")
                if (
                    citizen.conversation_state == "AWAITING_LOCATION"
                    and pending.get("media_id") == media_id
                ):
                    reply = strings["ask_location"]
                    WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
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
                    "image_url": stored_ref,
                    "media_id": media_id,
                    "mime_type": media_res.get("mime_type"),
                    "sha256": media_res.get("sha256"),
                    "file_size": media_res.get("file_size"),
                    "waste_type": "Mixed Municipal Waste"
                })
                db.commit()

                reply = strings["ask_location"]
                WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
                return {"status": "awaiting_location", "reply": reply, "image_url": stored_ref}

            elif media_url:
                citizen.conversation_state = "AWAITING_LOCATION"
                citizen.pending_complaint_data = json.dumps({
                    "image_url": media_url,
                    "waste_type": "Mixed Municipal Waste"
                })
                db.commit()

                reply = strings["ask_location"]
                WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
                return {"status": "awaiting_location", "reply": reply, "image_url": media_url}

            else:
                reply = strings.get("image_error")
                WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
                return {"status": "media_error", "reply": reply, "error": "No media identifier provided"}

        # ----------------------------------------------------------------
        # STEP 3: Multi-Step Reporting State Machine: Location Pin Ingestion
        # ----------------------------------------------------------------
        if message_type == "location" or (latitude is not None and longitude is not None):
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
                WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
                return {"status": "invalid_location", "reply": reply}

            # Recovery Check: If this inbound message already created a complaint (e.g. post-commit failure retry),
            # recover and return the original confirmation without repeating business side-effects or re-prompting.
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

            # Dynamically select an eligible registered driver by least active workload
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

            # Build a clean location address from geotagged coordinates
            location_address = f"Geotagged via WhatsApp ({lat_val:.4f}, {lng_val:.4f}), Dhule"
            if citizen.ward:
                location_address = f"{citizen.ward}, {location_address}"

            # Persist complaint atomically: complaint + driver task + EcoCoin award +
            # processed-message correlation.  A bounded retry loop retries only when
            # the database raises a duplicate-key error specifically for tracking_number;
            # all other errors propagate immediately.
            new_complaint = None
            ticket_num = None
            # Snapshot mutable citizen state so we can restore it on a failed attempt
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
                    db.flush()  # raises IntegrityError here on duplicate tracking_number

                    # --- all writes below are inside the same transaction ---
                    # Auto-assign driver task in tasks table
                    new_task = DriverTask(
                        driver_id=assigned_driver_id,
                        complaint_id=new_complaint.id,
                        location_name=new_complaint.location_address,
                        status="Pending",
                        route_order=1
                    )
                    db.add(new_task)

                    # Award citizen +20 EcoCoins (in-memory mutations inside the transaction)
                    citizen.eco_coins = _coins_before + 20
                    if citizen_user:
                        citizen_user.eco_coins = (citizen_user.eco_coins or 100) + 20
                    citizen.conversation_state = "IDLE"
                    citizen.pending_complaint_data = None

                    # Correlate processed-message record with this complaint
                    if message_id:
                        from server.models.whatsapp_session import WhatsAppProcessedMessage
                        db.query(WhatsAppProcessedMessage).filter(
                            WhatsAppProcessedMessage.message_id == message_id
                        ).update({
                            "complaint_id": new_complaint.id
                        })

                    db.commit()  # single atomic commit for all writes above
                    break  # success — exit retry loop

                except Exception as exc:
                    db.rollback()
                    # Restore in-memory citizen state so a retry starts clean
                    citizen.eco_coins = _coins_before
                    citizen.conversation_state = _state_before
                    citizen.pending_complaint_data = _pending_before

                    if _is_tracking_number_collision(exc):
                        if _attempt < _WA_MAX_RETRIES - 1:
                            logger.warning(
                                "[WHATSAPP COMPLAINT] Tracking number collision on attempt %d/%d (%s); retrying.",
                                _attempt + 1,
                                _WA_MAX_RETRIES,
                                ticket_num,
                            )
                            continue
                        raise RuntimeError(
                            f"Could not generate a unique WhatsApp tracking number after {_WA_MAX_RETRIES} attempts."
                        ) from exc
                    logger.error(
                        "[WHATSAPP COMPLAINT] Failed to atomically persist complaint and task: %s", exc
                    )
                    raise

            reply = strings["report_success"].format(
                ticket=ticket_num,
                location=location_address,
                driver=driver_display,
                coins=citizen.eco_coins
            )
            WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
            return {"status": "complaint_created", "ticket": ticket_num, "reply": reply}

        # ----------------------------------------------------------------
        # STEP 4: Dashboard Menu Selection Routing (9 options)
        # ----------------------------------------------------------------
        lowered = clean_text.lower()

        # Option 1: Report Waste
        if clean_text == "1" or "report" in lowered or "तक्रार नोंद" in lowered:
            citizen.conversation_state = "AWAITING_PHOTO"
            db.commit()
            reply = strings["ask_photo"]
            WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
            return {"status": "awaiting_photo", "reply": reply}

        # Option 2: General Complaint
        if clean_text == "2" or "general" in lowered or "सामान्य" in lowered:
            citizen.conversation_state = "AWAITING_GENERAL_COMPLAINT"
            db.commit()
            reply = strings["general_complaint_prompt"]
            WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
            return {"status": "awaiting_general_complaint", "reply": reply}

        # Handle AWAITING_GENERAL_COMPLAINT state — create a general complaint from free text
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
                        location_address=f"Dhule (reported via WhatsApp text)",
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
            WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
            return {"status": "general_complaint_created", "ticket": ticket_num, "reply": reply}

        # Option 3: Garbage Truck Tracking (stub — no live GPS available)
        if clean_text == "3" or "truck" in lowered or "घंटागाडी" in lowered or "गाडी" in lowered:
            reply = strings["truck_unavailable"]
            WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
            return {"status": "truck_unavailable", "reply": reply}

        # Option 4: Collection Schedule (stub — not yet available)
        if clean_text == "4" or "schedule" in lowered or "वेळापत्रक" in lowered:
            reply = strings["schedule_unavailable"]
            WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
            return {"status": "schedule_unavailable", "reply": reply}

        # Option 5: Eco Wallet
        if clean_text == "5" or "wallet" in lowered or "coin" in lowered or "वॉलेट" in lowered:
            reply = strings["wallet_info"].format(
                coins=citizen.eco_coins,
                rupees=citizen.eco_coins // 2
            )
            WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
            return {"status": "wallet_info", "reply": reply}

        # Option 6: My Complaints
        if clean_text == "6" or "track" in lowered or "स्थिती" in lowered or "my complaint" in lowered:
            # Query by whatsapp_citizen_id OR citizen_id (user_id from link)
            identity_filters = [Complaint.whatsapp_citizen_id == citizen.id]
            if citizen.user_id:
                identity_filters.append(Complaint.citizen_id == citizen.user_id)
            complaints = db.query(Complaint).filter(
                or_(*identity_filters)
            ).order_by(Complaint.id.desc()).limit(5).all()
            if not complaints:
                reply = strings["no_complaints"]
            else:
                lines = [strings["complaints_header"]]
                for c in complaints:
                    status_icon = "⏳" if c.status == "Pending" else ("🚚" if c.status == "In Progress" else "✅")
                    lines.append(
                        f"{status_icon} *#{c.tracking_number}*\n"
                        f"प्रकार: {c.waste_type}\nस्थिती: *{c.status}*\n"
                        f"चालक: {c.assigned_driver_name or ('नियुक्त केला जात आहे' if lang == 'mr' else 'Pending')}\n"
                    )
                reply = "\n".join(lines)
            WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
            return {"status": "track_complaints", "reply": reply}

        # Option 7: Leaderboard (stub)
        if clean_text == "7" or "leaderboard" in lowered or "लीडर" in lowered:
            reply = strings["leaderboard_unavailable"].format(coins=citizen.eco_coins)
            WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
            return {"status": "leaderboard_unavailable", "reply": reply}

        # Option 8: Municipal Notices (stub)
        if clean_text == "8" or "notice" in lowered or "सूचना" in lowered:
            reply = strings["notices_unavailable"]
            WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
            return {"status": "notices_unavailable", "reply": reply}

        # Option 9: Help / Switch Language
        if (clean_text == "9" or "help" in lowered or "भाषा" in lowered
                or "english" in lowered or "marathi" in lowered or "मराठी" in lowered):
            # Switch language if requested
            if "english" in lowered:
                new_lang = "en"
                citizen.preferred_language = new_lang
                db.commit()
                new_strings = TEXTS[new_lang]
                reply = new_strings["lang_switched"] + "\n\n" + new_strings["menu_options"]
            elif "marathi" in lowered or "मराठी" in lowered:
                new_lang = "mr"
                citizen.preferred_language = new_lang
                db.commit()
                new_strings = TEXTS[new_lang]
                reply = new_strings["lang_switched"] + "\n\n" + new_strings["menu_options"]
            else:
                reply = strings["help_text"]
            WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
            return {"status": "help", "reply": reply}

        # Default Fallback: Present Dashboard Menu
        citizen_name = "Citizen"
        if citizen.user_id:
            user_obj = db.query(User).filter(User.id == citizen.user_id).first()
            if user_obj and user_obj.full_name:
                citizen_name = user_obj.full_name
        elif citizen.full_name and citizen.full_name != "Shirpur Resident":
            citizen_name = citizen.full_name

        reply = strings["authorized_welcome"].format(
            name=citizen_name,
            coins=citizen.eco_coins,
            rupees=citizen.eco_coins // 2
        ) + "\n\n" + strings["menu_options"]
        WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
        return {"status": "menu_presented", "reply": reply}
