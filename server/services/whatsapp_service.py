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
from sqlalchemy import or_, inspect, func
from server.utils.config import config, is_local_or_test_environment
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

    Format: EVT-2026-<8 uppercase alphanumeric chars>
    Total length: 17 chars — fits String(32).
    """
    suffix = "".join(secrets.choice(_ID_ALPHABET) for _ in range(8))
    year = datetime.now(timezone.utc).year
    return f"EVT-{year}-{suffix}"


def _is_column_in_table(db: Session, table_name: str, column_name: str) -> bool:
    """Check whether a column actually exists in the database table schema.
    Use this guard before accessing IAM/Municipal columns that may not exist
    in older database deployments (e.g. is_locked, account_status).
    """
    try:
        bind = db.get_bind()
        insp = inspect(bind)
        cols = {c["name"] for c in insp.get_columns(table_name)}
        return column_name in cols
    except Exception:
        return False


def _generate_whatsapp_tracking_id(ward: str) -> str:
    """Generate a collision-resistant WhatsApp complaint tracking number.

    Format: <PREFIX>2026-W<ward_number>-<9 uppercase alphanumeric chars>
    Example: DHL-2026-W12-A7BZ3XKQR
    Total length: ≤ 28 chars — fits String(30).
    """
    prefix = getattr(config, "TRACKING_PREFIX", "DHL-").rstrip("-") + "-"
    ward_num = ward.replace("Ward ", "").strip() if ward else "0"
    suffix = "".join(secrets.choice(_ID_ALPHABET) for _ in range(_ID_SUFFIX_LEN))
    year = datetime.now(timezone.utc).year
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
from server.services.whatsapp_templates import WhatsAppTemplates, build_response_templates


def _build_texts() -> dict:
    """Return bilingual UI copy for Dhule Municipal Corporation via WhatsAppTemplates."""
    return build_response_templates()


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
                preferred_language=None,          # triggers AWAITING_LANGUAGE flow
                eco_coins=0,
                conversation_state="AWAITING_LANGUAGE"
            )
            db.add(citizen)
            db.commit()
            db.refresh(citizen)
        elif citizen.full_name in {"Shirpur Resident", "Dhule Citizen"}:
            citizen.full_name = "WhatsApp Citizen"
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
    def authoritative_linked_citizen_ward(
        citizen: WhatsAppCitizen, citizen_user: Optional[User]
    ) -> Optional[str]:
        """Return the server-side profile ward only for a linked WhatsApp identity.

        Legacy QR values and WhatsAppCitizen.ward can originate from user input,
        so they are never an assignment authority.
        """
        if not citizen.user_id or not citizen_user or citizen_user.id != citizen.user_id:
            return None
        ward = (citizen_user.ward or "").strip()
        if not ward or ward.casefold() == "unassigned":
            return None
        return ward

    @staticmethod
    def select_eligible_driver(db: Session, complaint_ward: Optional[str] = None) -> Optional[User]:
        """
        Selects an eligible registered driver using deterministic least-active-workload.
        Workload = count of tasks with status 'Pending' or 'In Progress'.
        Ties are broken deterministically by driver.id ascending.
        Returns None if no eligible driver is available.
        """
        requested_ward = (complaint_ward or "").strip()
        if not requested_ward:
            logger.warning(
                "[DRIVER ASSIGNMENT] No validated complaint ward; leaving complaint unassigned."
            )
            return None

        ward_key = requested_ward.casefold()
        eligible_drivers = db.query(User).filter(
            User.role == "driver",
            User.is_active.is_(True),
            User.is_locked.is_(False),
            User.is_verified.is_(True),
            User.account_status == "active",
            User.ward.is_not(None),
            func.trim(User.ward) != "",
            func.lower(func.trim(User.ward)) == ward_key,
        ).all()

        if not eligible_drivers:
            logger.info(
                "[DRIVER ASSIGNMENT] No active, verified Driver for complaint ward '%s'; leaving complaint unassigned.",
                requested_ward,
            )
            return None

        # Calculate active workload for each eligible driver
        driver_workloads = []
        for d in eligible_drivers:
            # Strictly ensure driver role
            if d.role != "driver":
                continue
            active_task_count = db.query(DriverTask).filter(
                DriverTask.driver_id == d.id,
                DriverTask.status.in_([
                    "Pending", "Accepted", "In Progress", "Evidence Submitted",
                    "Pending Verification", "Requires Rework",
                ])
            ).count()
            driver_workloads.append((active_task_count, d.id, d))

        if not driver_workloads:
            return None

        # Sort by least active tasks first, then by driver id ascending (deterministic)
        driver_workloads.sort(key=lambda item: (item[0], item[1]))
        selected_driver = driver_workloads[0][2]
        logger.info(
            f"[DRIVER ASSIGNMENT] Selected driver {selected_driver.full_name} "
            f"(ID: {selected_driver.id}, ward: {selected_driver.ward}, active tasks: {driver_workloads[0][0]})"
        )
        return selected_driver


    @staticmethod
    def build_full_menu_text(citizen=None, db=None, lang: str = "mr") -> str:
        """Construct the complete 8-option full menu text matching reference layout.

        Visual structure:
        - Municipal Heading: EcoPulse AI — Municipal Services
        - Localized Greeting: नमस्कार! Hello! 👋
        - Account Info & EcoCoin Balance (where applicable)
        - Service Selection Prompt: Please select a service / कृपया सेवा निवडा:
        - Numbered Services 1–8 with icons
        - Quick actions section: ⚡ Quick actions / झटपट सेवा
        """
        is_mr = (lang or "mr").lower() == "mr"

        # 1. Municipal Heading
        heading = (
            "🏛️ *EcoPulse AI — Municipal Services / नागरी सेवा*"
            if not is_mr
            else "🏛️ *EcoPulse AI — नागरी सेवा / Municipal Services*"
        )

        # 2. Localized Greeting & Account Info
        c_name = ""
        if citizen and db:
            if getattr(citizen, "user_id", None):
                u_obj = db.query(User).filter(User.id == citizen.user_id).first()
                if u_obj and u_obj.full_name:
                    c_name = u_obj.full_name
            elif getattr(citizen, "full_name", None) and citizen.full_name != "Shirpur Resident":
                c_name = citizen.full_name

        coins = (getattr(citizen, "eco_coins", 0) or 0) if citizen else 0
        rupees = coins // 2

        if c_name:
            greeting = f"नमस्कार {c_name}! Hello! 👋" if is_mr else f"Hello {c_name}! नमस्कार! 👋"
            account_line = (
                f"✅ आपले EcoPulse खाते सक्रिय आहे.\n🪙 *ईको-कॉइन्स शिल्लक: {coins} गुण (₹{rupees} कर सवलत)*"
                if is_mr
                else f"✅ Your EcoPulse account is active.\n🪙 *EcoCoin Balance: {coins} pts (₹{rupees} rebate)*"
            )
        elif coins > 0:
            greeting = "नमस्कार! Hello! 👋"
            account_line = (
                f"🪙 *ईको-कॉइन्स शिल्लक: {coins} गुण (₹{rupees} कर सवलत)*"
                if is_mr
                else f"🪙 *EcoCoin Balance: {coins} pts (₹{rupees} rebate)*"
            )
        else:
            greeting = "नमस्कार! Hello! 👋"
            account_line = ""

        # 3. Prompt
        prompt = (
            "कृपया खालीलपैकी सेवा निवडा / Please select a service:"
            if is_mr
            else "Please select a service / कृपया खालीलपैकी सेवा निवडा:"
        )

        # 4. Numbered 1-8 Services
        if is_mr:
            services = (
                "1. 🗑️ कचरा नोंदवा / Report Waste\n"
                "2. ⚠️ सामान्य तक्रार / General Complaint\n"
                "3. 🚛 घंटागाडी ट्रॅकिंग / Garbage Vehicle Tracking\n"
                "4. 🗓️ संकलन वेळापत्रक / Collection Schedule\n"
                "5. 🪙 इको-वॉलेट आणि रिवॉर्ड्स / EcoWallet & Rewards\n"
                "6. 📋 माझ्या तक्रारी / My Complaints\n"
                "7. 🏆 महापालिका सूचना / Municipal Notices\n"
                "8. ❓ मदत आणि भाषा / Help & Language"
            )
        else:
            services = (
                "1. 🗑️ Report Waste / कचरा नोंदवा\n"
                "2. ⚠️ General Complaint / सामान्य तक्रार\n"
                "3. 🚛 Garbage Vehicle Tracking / घंटागाडी ट्रॅकिंग\n"
                "4. 🗓️ Collection Schedule / संकलन वेळापत्रक\n"
                "5. 🪙 EcoWallet & Rewards / इको-वॉलेट आणि रिवॉर्ड्स\n"
                "6. 📋 My Complaints / माझ्या तक्रारी\n"
                "7. 🏆 Municipal Notices / महापालिका सूचना\n"
                "8. ❓ Help & Language / मदत आणि भाषा"
            )

        # 5. Quick actions section
        quick_actions = (
            "⚡ *Quick actions / झटपट सेवा*\n"
            "👉 *क्रमांक (1-8) पाठवा किंवा खालील बटण दाबा:*"
            if is_mr
            else "⚡ *Quick actions / झटपट सेवा*\n"
            "👉 *Reply with a number (1-8) or select a quick action below:*"
        )

        parts = [heading, greeting]
        if account_line:
            parts.append(account_line)
        parts.append(prompt)
        parts.append(services)
        parts.append(quick_actions)

        return "\n\n".join(parts)


    @staticmethod
    def build_language_selection_interactive(body_text: Optional[str] = None) -> dict:
        """Construct a Meta WhatsApp Cloud API reply button payload for language selection.

        Presents two buttons: English (LANG_EN) and मराठी (LANG_MR).
        Sent to first-time citizens whose conversation_state == 'AWAITING_LANGUAGE'.
        """
        text = body_text or (
            "Welcome to EcoPulse AI 🏛️\n\n"
            "Choose your preferred language / कृपया भाषा निवडा"
        )
        return WhatsAppService.build_quick_buttons_interactive(
            body_text=text,
            buttons=[
                ("LANG_EN", "English"),
                ("LANG_MR", "मराठी"),
            ],
            header_text="EcoPulse AI",
            footer_text="Dhule Municipal Corporation"
        )

    @staticmethod
    def build_primary_buttons_interactive(lang: str = "mr", body_text: Optional[str] = None) -> dict:
        """Construct a Meta WhatsApp Cloud API reply button payload for the 3 primary service buttons.

        Titles are kept ≤ 20 characters to comply with Meta Cloud API limits.
        Sent after language selection and to returning users on the main menu.
        """
        is_mr = (lang or "mr").lower() == "mr"
        if not body_text:
            body_text = (
                "EcoPulse AI — नागरी सेवा\n\nआज आम्ही आपली कशी मदत करू शकतो?"
                if is_mr
                else "EcoPulse AI — Citizen Services\n\nHow can we assist you today?"
            )
        buttons = (
            [
                ("REPORT_WASTE",        "🗑️ कचरा नोंदवा"),
                ("GENERAL_COMPLAINT",   "💬 सामान्य तक्रार"),
                ("OPEN_FULL_MENU",      "📋 पूर्ण मेनू"),
            ]
            if is_mr
            else [
                ("REPORT_WASTE",        "🗑️ Report Waste"),
                ("GENERAL_COMPLAINT",   "💬 General Complaint"),
                ("OPEN_FULL_MENU",      "📋 Open Full Menu"),
            ]
        )
        footer = "धुळे महानगरपालिका" if is_mr else "Dhule Municipal Corporation"
        return WhatsAppService.build_quick_buttons_interactive(
            body_text=body_text,
            buttons=buttons,
            footer_text=footer
        )

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
                "title": "🗑️ कचरा / Report Waste",
                "description": "कचरा तक्रार नोंदवा / Report waste"
            },
            {
                "id": "MENU_GENERAL_COMPLAINT",
                "title": "⚠️ तक्रार / Complaint",
                "description": "सामान्य तक्रार / General complaint"
            },
            {
                "id": "MENU_VEHICLE_TRACKING",
                "title": "🚛 घंटागाडी / Tracking",
                "description": "घंटागाडी ट्रॅकिंग / Vehicle tracking"
            },
            {
                "id": "MENU_COLLECTION_SCHEDULE",
                "title": "📅 वेळापत्रक / Schedule",
                "description": "संकलन वेळापत्रक / Collection schedule"
            },
            {
                "id": "MENU_ECO_WALLET",
                "title": "🪙 इको-वॉलेट / Rewards",
                "description": "इको-वॉलेट आणि रिवॉर्ड्स / EcoWallet & rewards"
            },
            {
                "id": "MENU_MY_COMPLAINTS",
                "title": "📋 तक्रारी / Complaints",
                "description": "माझ्या तक्रारी तपासा / My complaints status"
            },
            {
                "id": "MENU_NOTICES",
                "title": "🏛️ सूचना / Notices",
                "description": "महानगरपालिका सूचना / Municipal notices"
            },
            {
                "id": "MENU_HELP_LANG",
                "title": "❓ मदत / Help & Lang",
                "description": "मदत व भाषा बदला / Help & change language"
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
                "title": "🎉 सार्वजनिक / Public",
                "description": "सार्वजनिक कार्यक्रम / Public Event"
            },
            {
                "id": "EVENT_CAT_RELIGIOUS",
                "title": "🙏 धार्मिक / Religious",
                "description": "धार्मिक कार्यक्रम / Religious Event"
            },
            {
                "id": "EVENT_CAT_WEDDING",
                "title": "💍 लग्न / Wedding",
                "description": "लग्न समारंभ / Wedding"
            },
            {
                "id": "EVENT_CAT_FESTIVAL",
                "title": "🎊 उत्सव / Festival",
                "description": "उत्सव / Festival"
            },
            {
                "id": "EVENT_CAT_SCHOOL",
                "title": "🏫 शाळा/कॉलेज / School",
                "description": "कॉलेज किंवा शाळेचा कार्यक्रम / College or School Event"
            },
            {
                "id": "EVENT_CAT_CLEANUP",
                "title": "🧹 स्वच्छता / Clean-up",
                "description": "स्वच्छता अभियान / Clean-up Drive"
            },
            {
                "id": "EVENT_CAT_OTHER",
                "title": "📌 इतर / Other",
                "description": "इतर कार्यक्रम / Other Event"
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
            to_phone,
            fallback_text or body_text,
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
        """Send a native Meta interactive reply button message with plain text fallback."""
        interactive = WhatsAppService.build_quick_buttons_interactive(
            body_text=body_text,
            buttons=buttons,
            header_text=header_text,
            footer_text=footer_text
        )
        return WhatsAppService.send_meta_whatsapp(
            to_phone,
            fallback_text or body_text,
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
            if is_local_or_test_environment(config.ENV):
                logger.info("[META WHATSAPP] Outbound message skipped in local/test without provider credentials.")
                return {
                    "status": "simulated",
                    "type": "interactive" if interactive else "text",
                    "interactive": interactive
                }
            logger.error("[META WHATSAPP] Provider configuration is missing outside local/test.")
            raise RetryableWhatsAppError("Meta WhatsApp delivery is not configured")

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
                # If interactive delivery returns 400 client error, fallback to text
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
        location_name: Optional[str] = None,
        location_address: Optional[str] = None,
        message_id: str = None
    ) -> dict:
        """
        Central message handling engine for WhatsApp.
        Implements language-first gate, Gemini conversational intelligence,
        interactive menu options, complaint workflows, and EventReport flow.
        """
        citizen = WhatsAppService.get_or_create_citizen(db, sender_phone)
        normalized_phone = WhatsAppService.normalize_phone(sender_phone)
        lang = citizen.preferred_language or "mr"
        all_texts = _build_texts()
        strings = all_texts.get(lang, all_texts["mr"])
        clean_text = (text_body or "").strip()
        media_url = (media_url or "").strip()

        # Account lifecycle applies before VERIFY/LINK/legacy QR commands too.
        # Never let those pre-auth commands revive or operate a suspended/retired identity.
        short_phone = normalized_phone[2:] if normalized_phone.startswith("91") and len(normalized_phone) == 12 else normalized_phone
        candidate_phones = {normalized_phone, short_phone, f"+91{short_phone}", f"0{short_phone}"}
        # Use IAM-aware schema inspection (supports PostgreSQL IAM + SQLite test env)
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
        # STEP 0b: Legacy QR code authorization support (backward compatibility)
        # ----------------------------------------------------------------
        qr_match = re.search(r'(?:JOIN\s+)?(SHP[-_]W(\d+)[-_]H([A-Za-z0-9]+))', clean_text, re.IGNORECASE)
        if qr_match:
            full_code = qr_match.group(1).upper()
            ward_num = qr_match.group(2)
            citizen.household_id = full_code
            citizen.ward = f'Ward {ward_num}'
            citizen.is_authorized = True

            # QR authorization: if no language saved, go to language selection
            if not citizen.preferred_language:
                citizen.conversation_state = 'AWAITING_LANGUAGE'
                db.commit()
                lang_sel = WhatsAppService.build_language_selection_interactive()
                prompt_text = "Welcome to EcoPulse AI\n\nChoose your preferred language / कृपया भाषा निवडा"
                WhatsAppService.send_meta_whatsapp(
                    citizen.phone_number,
                    prompt_text,
                    interactive=lang_sel
                )
                return {
                    'status': 'awaiting_language',
                    'citizen': citizen.phone_number,
                    'reply': prompt_text,
                    'household_id': citizen.household_id,
                    'ward': citizen.ward,
                }
            else:
                citizen.conversation_state = 'IDLE'
                db.commit()
                reply = strings['authorized_welcome'].format(
                    name=citizen.full_name or 'Citizen',
                    coins=citizen.eco_coins,
                    rupees=citizen.eco_coins // 2
                ) + f"\n📍 प्रभाग: {citizen.ward} | घर क्र.: {citizen.household_id}\n\n" + strings["menu_options"]
                WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
                return {'status': 'authorized', 'citizen': citizen.phone_number, 'reply': reply}

        lowered = clean_text.lower()

        # ----------------------------------------------------------------
        # STEP 1: Language Selection Gate — Every WhatsApp citizen must
        # select Marathi or English before receiving onboarding menus.
        # Executes BEFORE citizen authorization.
        # ----------------------------------------------------------------
        _lang_selection_cmds = {"START", "LANGUAGE", "LANG", "CHANGE LANGUAGE", "CHANGE_LANGUAGE", "भाषा बदला"}

        _has_saved_lang = bool(
            citizen.preferred_language
            and str(citizen.preferred_language).strip().lower() in {"en", "mr"}
        )
        _in_lang_state = citizen.conversation_state == "AWAITING_LANGUAGE"
        _explicit_lang_cmd = (clean_text.upper() in _lang_selection_cmds) or (lowered in {"change language", "भाषा बदला"})
        _is_conversational_msg = message_type in {"text", "interactive"}
        _in_active_workflow = citizen.conversation_state in {
            "AWAITING_PHOTO", "AWAITING_LOCATION", "AWAITING_GENERAL_COMPLAINT",
            "AWAITING_EVENT_CATEGORY", "AWAITING_EVENT_DATE", "AWAITING_EVENT_TIME",
            "AWAITING_EVENT_LOCATION", "AWAITING_EVENT_CONFIRMATION",
            "AWAITING_EVENT_ATTENDEES", "AWAITING_EVENT_DESCRIPTION", "AWAITING_EVENT_CONFIRM"
        }

        if _is_conversational_msg and not _in_active_workflow and (_in_lang_state or _explicit_lang_cmd or not _has_saved_lang):
            # Determine whether this message is a valid language choice:
            # - Interactive button IDs (LANG_EN, LANG_MR) are always accepted
            # - Plain-text words and numeric digits accepted ONLY in AWAITING_LANGUAGE
            _chose_en = (
                clean_text == "LANG_EN"
                or (_in_lang_state and (clean_text == "1" or lowered in {"english", "1", "en", "eng", "इंग्रजी"} or bool(re.search(r"\b(english|eng|en|इंग्रजी)\b", lowered))))
            ) and not _explicit_lang_cmd

            _chose_mr = (
                clean_text == "LANG_MR"
                or (_in_lang_state and (clean_text == "2" or lowered in {"marathi", "मराठी", "2", "mr"} or bool(re.search(r"\b(marathi|मराठी|mr)\b", lowered))))
            ) and not _explicit_lang_cmd

            if _chose_en or _chose_mr:
                chosen_lang = "en" if _chose_en else "mr"
                citizen.preferred_language = chosen_lang
                citizen.conversation_state = "IDLE"
                db.commit()
                lang = chosen_lang
                all_texts = _build_texts()
                strings = all_texts[chosen_lang]

                # Enforce authorization in chosen language
                is_linked_check = bool(citizen.user_id or citizen.is_authorized)
                if not is_linked_check:
                    reply = strings["not_linked_prompt"]
                    WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
                    return {"status": "not_linked", "language": chosen_lang, "reply": reply}

                welcome_txt = WhatsAppService.build_full_menu_text(citizen, db, lang=chosen_lang)
                primary_btns = WhatsAppService.build_primary_buttons_interactive(lang=chosen_lang, body_text=welcome_txt)
                WhatsAppService.send_meta_whatsapp(
                    citizen.phone_number, welcome_txt, interactive=primary_btns
                )
                return {"status": "language_selected", "language": chosen_lang, "reply": welcome_txt}

            # Not a language choice — prompt language selection and persist state
            citizen.conversation_state = "AWAITING_LANGUAGE"
            db.commit()
            is_marathi_greeting = any(w in lowered for w in ["नमस्कार", "नमस्ते", "namaskar", "namaste"])
            is_english_greeting = any(w in lowered for w in ["hello", "hi", "hey", "good morning", "start"])
            if is_marathi_greeting:
                prompt_text = WhatsAppTemplates.build_language_selection_prompt("mr")
            elif is_english_greeting:
                prompt_text = WhatsAppTemplates.build_language_selection_prompt("en")
            else:
                prompt_text = WhatsAppTemplates.build_language_selection_prompt("bilingual")

            lang_sel = WhatsAppService.build_language_selection_interactive(body_text=prompt_text)
            WhatsAppService.send_meta_whatsapp(
                citizen.phone_number,
                prompt_text,
                interactive=lang_sel
            )
            return {"status": "awaiting_language", "reply": prompt_text}

        # ----------------------------------------------------------------
        # STEP 1b: Auth gatekeeper — citizen must have user_id (linked account)
        # Enforced after language selection is verified.
        # ----------------------------------------------------------------
        is_linked = bool(citizen.user_id or citizen.is_authorized)
        if not is_linked:
            reply = strings["not_linked_prompt"]
            WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
            return {"status": "not_linked", "reply": reply}

        # Greeting or Main Menu request for linked citizens
        is_full_menu_cmd = (
            clean_text in {"MENU_FULL_MENU", "FULL_MENU", "OPEN_FULL_MENU"}
            or lowered in {"full menu", "open full menu", "open menu", "पूर्ण मेनू"}
        )
        GREETING_WORDS = {
            "hey", "hello", "hi", "yoo", "yo", "namaskar", "namaste",
            "नमस्कार", "नमस्ते", "menu", "start"
        }
        _clean_letters = re.sub(r'[^a-zA-Z\u0900-\u097F]', '', lowered)
        is_menu_cmd = (
            lowered in GREETING_WORDS
            or _clean_letters in GREETING_WORDS
            or any(lowered.startswith(w) for w in ["hey", "hello", "hi", "yoo", "yo", "namaskar", "namaste", "नमस्कार", "नमस्ते"])
            or clean_text in {"MENU_MAIN", "MAIN_MENU", "MENU_BACK", "BACK_TO_MENU"}
        )

        def _present_main_menu(extra_note: str = ""):
            if citizen.conversation_state != "IDLE":
                citizen.conversation_state = "IDLE"
                citizen.pending_complaint_data = None
                db.commit()

            menu_txt = WhatsAppService.build_full_menu_text(citizen, db, lang=lang)
            if extra_note:
                menu_txt = extra_note + "\n\n" + menu_txt

            primary_btns = WhatsAppService.build_primary_buttons_interactive(lang=lang, body_text=menu_txt)
            WhatsAppService.send_meta_whatsapp(
                citizen.phone_number,
                message_text=menu_txt,
                interactive=primary_btns
            )
            return {"status": "menu_presented", "reply": menu_txt}

        def _present_full_menu():
            if citizen.conversation_state != "IDLE":
                citizen.conversation_state = "IDLE"
                citizen.pending_complaint_data = None
                db.commit()

            full_menu_text = WhatsAppService.build_full_menu_text(citizen, db, lang=lang)
            interactive_btns = WhatsAppService.build_primary_buttons_interactive(
                lang=lang,
                body_text=full_menu_text
            )
            WhatsAppService.send_meta_whatsapp(
                citizen.phone_number,
                message_text=full_menu_text,
                interactive=interactive_btns
            )
            return {"status": "full_menu_presented", "reply": full_menu_text}

        if is_full_menu_cmd:
            return _present_full_menu()

        if is_menu_cmd:
            return _present_main_menu()

        # ----------------------------------------------------------------
        # GLOBAL CANCELLATION: Return to IDLE from any in-flight state
        # ----------------------------------------------------------------
        if clean_text.upper() in {"CANCEL", "EXIT", "QUIT", "रद्द", "रद्द करा"} or lowered in {"cancel", "exit", "quit", "रद्द", "रद्द करा"}:
            if citizen.conversation_state != "IDLE":
                citizen.conversation_state = "IDLE"
                citizen.pending_complaint_data = None
                db.commit()
                reply = "❌ प्रक्रिया रद्द करण्यात आली आहे. / Process cancelled.\n\n" + strings["menu_options"]
                WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
                return {"status": "cancelled", "reply": reply}

        # ----------------------------------------------------------------
        # EVENT REPORTING STATE MACHINE
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
                        explicit_parts = [
                            str(p).strip() for p in (location_name, location_address)
                            if p and str(p).strip()
                        ]
                        if explicit_parts:
                            loc_addr = f"{', '.join(explicit_parts)} ({lat_val:.6f}, {lng_val:.6f})"
                        else:
                            loc_addr = f"Geotagged via WhatsApp ({lat_val:.6f}, {lng_val:.6f})"
                        loc_captured = True
                except (TypeError, ValueError):
                    pass

            elif clean_text.upper().startswith("ADDRESS:") or clean_text.startswith("पत्ता:"):
                manual_address = clean_text.split(":", 1)[1].strip()
                if manual_address:
                    loc_addr = manual_address
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
                    parsed_date = datetime.strptime(raw_date, "%d/%m/%Y").date()
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
                    date=pending.get("event_date_display") or pending.get("event_date"),
                    time=pending.get("event_time"),
                    location=pending.get("location_address")
                )
                btn = [("MENU_MAIN", "📋 मेनू / Main Menu")]
                interactive = WhatsAppService.build_quick_buttons_interactive(reply, btn)
                WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply, interactive=interactive)
                return {"status": "event_created", "reference_id": ref_id, "reply": reply}

            elif clean_text in {"EVENT_CANCEL", "2"} or lowered in {"cancel", "रद्द", "no", "नाही"}:
                citizen.conversation_state = "IDLE"
                citizen.pending_complaint_data = None
                db.commit()
                reply = strings["event_cancelled"]
                btn = [("MENU_MAIN", "📋 मेनू / Main Menu")]
                interactive = WhatsAppService.build_quick_buttons_interactive(reply, btn)
                WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply, interactive=interactive)
                return {"status": "event_cancelled", "reply": reply}

            elif clean_text in {"EVENT_EDIT", "3"} or lowered in {"edit", "बदला"}:
                pending = json.loads(citizen.pending_complaint_data or "{}")
                pending["flow"] = "event"
                citizen.conversation_state = "AWAITING_EVENT_CATEGORY"
                citizen.pending_complaint_data = json.dumps(pending)
                db.commit()
                reply = strings["event_category_prompt"]
                cat_list = WhatsAppService.build_event_categories_interactive(lang)
                WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply, interactive=cat_list)
                return {"status": "awaiting_event_category", "reply": reply}

            else:
                pending = json.loads(citizen.pending_complaint_data or "{}")
                summary_text = strings["event_summary"].format(
                    category=pending.get("category", "Public Event"),
                    date=pending.get("event_date_display") or pending.get("event_date"),
                    time=pending.get("event_time"),
                    location=pending.get("location_address")
                )
                confirm_buttons = [
                    ("EVENT_CONFIRM", "✅ Confirm / खात्री"),
                    ("EVENT_CANCEL", "❌ Cancel / रद्द")
                ]
                interactive = WhatsAppService.build_quick_buttons_interactive(summary_text, confirm_buttons)
                WhatsAppService.send_meta_whatsapp(citizen.phone_number, summary_text, interactive=interactive)
                return {"status": "awaiting_event_confirmation", "reply": summary_text}

        # ----------------------------------------------------------------
        # WASTE LOCATION WAITING & MANUAL ADDRESS FALLBACK
        # ----------------------------------------------------------------
        manual_waste_address = None
        if citizen.conversation_state == "AWAITING_LOCATION" and message_type == "text":
            if clean_text.upper().startswith("ADDRESS:") or clean_text.startswith("पत्ता:"):
                manual_waste_address = clean_text.split(":", 1)[1].strip()
                if not manual_waste_address:
                    reply = strings["ask_location"]
                    WhatsAppService.send_meta_location_request(citizen.phone_number, reply)
                    return {"status": "awaiting_location", "reply": reply}
            else:
                reply = strings["ask_location"]
                WhatsAppService.send_meta_location_request(citizen.phone_number, reply)
                return {"status": "awaiting_location", "reply": reply}

        # In-flight guard: text message while awaiting photo repeats prompt
        if citizen.conversation_state == "AWAITING_PHOTO" and message_type == "text":
            reply = strings["ask_photo"]
            btn = [("MENU_MAIN", "मुख्य मेनू" if lang == "mr" else "Main Menu")]
            interactive = WhatsAppService.build_quick_buttons_interactive(reply, btn)
            WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply, interactive=interactive)
            return {"status": "awaiting_photo", "reply": reply}

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

                # Step 1: Confirm photo received
                photo_ack = strings.get("photo_received_ack", "📸 Photo received! / फोटो प्राप्त झाला! ✅")
                WhatsAppService.send_meta_whatsapp(citizen.phone_number, photo_ack)

                # Step 2 & 3: Send native WhatsApp location request message
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

            else:
                reply = strings.get("image_error")
                WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
                return {"status": "media_error", "reply": reply, "error": "No media identifier provided"}

        # ----------------------------------------------------------------
        # STEP 3: Multi-Step Reporting State Machine: Location Pin or Manual Address Ingestion
        # ----------------------------------------------------------------
        is_location_event = (message_type == "location" or (latitude is not None and longitude is not None))
        if is_location_event or manual_waste_address:
            # Recovery Check: If this inbound message already created a complaint, recover original confirmation
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
                            location=existing_complaint.location_address or "Location not provided",
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

            # If citizen is NOT awaiting waste location, do not process as waste complaint!
            if citizen.conversation_state != "AWAITING_LOCATION":
                # Check if there is pending photo or if they should be asked for a photo
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

            complaint_ward = WhatsAppService.authoritative_linked_citizen_ward(
                citizen, citizen_user
            )
            assigned_driver = WhatsAppService.select_eligible_driver(db, complaint_ward)
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
                location_address = manual_waste_address[:255]
            else:
                explicit_parts = [
                    str(p).strip() for p in (location_name, location_address)
                    if p and str(p).strip()
                ]
                if explicit_parts:
                    loc_desc = ", ".join(explicit_parts)
                    location_address = f"{loc_desc} ({lat_val:.4f}, {lng_val:.4f})"
                else:
                    location_address = f"Geotagged via WhatsApp ({lat_val:.4f}, {lng_val:.4f}), Dhule"
                if citizen.ward and citizen.ward not in location_address:
                    location_address = f"{citizen.ward}, {location_address}"

            new_complaint = None
            ticket_num = None
            _state_before = citizen.conversation_state
            _pending_before = citizen.pending_complaint_data
            for _attempt in range(_WA_MAX_RETRIES):
                ticket_num = _generate_whatsapp_tracking_id(complaint_ward or "0")
                try:
                    household_tag = f" {citizen.household_id}" if citizen.household_id else ""
                    description = f"Reported via WhatsApp by linked citizen{household_tag} (EcoPulse AI)."
                    new_complaint = Complaint(
                        tracking_number=ticket_num,
                        citizen_id=citizen_user_id,
                        whatsapp_citizen_id=citizen.id,
                        ward=complaint_ward or "Unassigned",
                        location_address=location_address,
                        latitude=lat_val,
                        longitude=lng_val,
                        waste_type=waste_type,
                        description=description,
                        image_url=image_url,
                        ai_status="Pending Review",
                        status="Pending",
                        assigned_driver_id=assigned_driver_id,
                        assigned_driver_name=assigned_driver_name
                    )
                    db.add(new_complaint)
                    db.flush()

                    if assigned_driver_id:
                        db.add(DriverTask(
                            driver_id=assigned_driver_id,
                            complaint_id=new_complaint.id,
                            location_name=new_complaint.location_address,
                            status="Pending",
                            route_order=1
                        ))
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
            report_buttons = [
                ("MENU_MY_COMPLAINTS", "माझ्या तक्रारी" if lang == "mr" else "My Complaints"),
                ("MENU_MAIN", "मुख्य मेनू" if lang == "mr" else "Main Menu")
            ]
            report_interactive = WhatsAppService.build_quick_buttons_interactive(reply, report_buttons)
            WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply, interactive=report_interactive)
            return {"status": "complaint_created", "ticket": ticket_num, "reply": reply}

        # ----------------------------------------------------------------
        # STEP 4: Dashboard Menu Selection Routing (8 options & Interactive Actions)
        # ----------------------------------------------------------------
        lowered = clean_text.lower()

        # Public Event Reporting Keyword / Interactive Action
        if clean_text in {"MENU_REPORT_EVENT", "EVENT", "EVENT_REPORT"} or "event" in lowered or "कार्यक्रम" in lowered or "समारंभ" in lowered or "इव्हेंट" in lowered:
            citizen.conversation_state = "AWAITING_EVENT_CATEGORY"
            citizen.pending_complaint_data = json.dumps({"flow": "event"})
            db.commit()
            reply = strings["event_category_prompt"]
            cat_list = WhatsAppService.build_event_categories_interactive(lang)
            WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply, interactive=cat_list)
            return {"status": "awaiting_event_category", "reply": reply}

        exact_menu_match = clean_text in {
            "1", "2", "3", "4", "5", "6", "7", "8", "9",
            "MENU_REPORT_WASTE", "REPORT_WASTE",
            "MENU_GENERAL_COMPLAINT", "GENERAL_COMPLAINT",
            "MENU_VEHICLE_TRACKING",
            "MENU_COLLECTION_SCHEDULE",
            "MENU_ECO_WALLET",
            "MENU_MY_COMPLAINTS",
            "MENU_NOTICES",
            "MENU_HELP_LANG",
            "MENU_REPORT_EVENT", "EVENT", "EVENT_REPORT",
            "LANG_EN", "LANG_MR",
            "MENU_FULL_MENU", "FULL_MENU", "OPEN_FULL_MENU",
        }

        # ----------------------------------------------------------------
        # GEMINI CONVERSATIONAL INTELLIGENCE (Phase 1)
        # Evaluates natural language messages before legacy keyword substrings.
        # Bypassed completely if citizen is in an active workflow or if an
        # exact button/numeric shortcut was tapped.
        # ----------------------------------------------------------------
        if not exact_menu_match and citizen.conversation_state == "IDLE" and clean_text:
            from server.services.gemini_service import GeminiService
            ai_res = GeminiService.classify_and_respond(clean_text, preferred_language=lang)
            if ai_res and not ai_res.is_fallback and ai_res.intent:
                if ai_res.intent == "GREETING":
                    return _present_main_menu()

                if ai_res.intent in {"REPORT_WASTE", "GARBAGE_NOT_COLLECTED"}:
                    citizen.conversation_state = "AWAITING_PHOTO"
                    db.commit()
                    reply = strings["ask_photo"]
                    btn = [("MENU_MAIN", "मुख्य मेनू" if lang == "mr" else "Main Menu")]
                    interactive = WhatsAppService.build_quick_buttons_interactive(reply, btn)
                    WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply, interactive=interactive)
                    return {"status": "awaiting_photo", "reply": reply, "ai_classified": True, "intent": ai_res.intent}

                if ai_res.intent == "GENERAL_COMPLAINT":
                    citizen.conversation_state = "AWAITING_GENERAL_COMPLAINT"
                    db.commit()
                    reply = strings["general_complaint_prompt"]
                    btn = [("MENU_MAIN", "मुख्य मेनू" if lang == "mr" else "Main Menu")]
                    interactive = WhatsAppService.build_quick_buttons_interactive(reply, btn)
                    WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply, interactive=interactive)
                    return {"status": "awaiting_general_complaint", "reply": reply, "ai_classified": True, "intent": "GENERAL_COMPLAINT"}

                if ai_res.intent == "TRACK_COMPLAINT":
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
                    return {"status": "track_complaints", "reply": reply, "ai_classified": True, "intent": "TRACK_COMPLAINT"}

                if ai_res.intent == "COLLECTION_SCHEDULE":
                    reply = strings.get("collection_schedule", strings.get("schedule_unavailable"))
                    btn = [("MENU_MAIN", "मुख्य मेनू" if lang == "mr" else "Main Menu")]
                    interactive = WhatsAppService.build_quick_buttons_interactive(reply, btn)
                    WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply, interactive=interactive)
                    return {"status": "collection_schedule", "reply": reply, "ai_classified": True, "intent": "COLLECTION_SCHEDULE"}

                if ai_res.intent == "TRACK_VEHICLE":
                    reply = strings["truck_unavailable"]
                    btn = [("MENU_MAIN", "मुख्य मेनू" if lang == "mr" else "Main Menu")]
                    interactive = WhatsAppService.build_quick_buttons_interactive(reply, btn)
                    WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply, interactive=interactive)
                    return {"status": "vehicle_tracking", "reply": reply, "ai_classified": True, "intent": "TRACK_VEHICLE"}

                if ai_res.intent == "CHECK_WALLET":
                    rupees = citizen.eco_coins // 2
                    reply = strings["wallet_info"].format(coins=citizen.eco_coins, rupees=rupees)
                    btn = [("MENU_MAIN", "मुख्य मेनू" if lang == "mr" else "Main Menu")]
                    interactive = WhatsAppService.build_quick_buttons_interactive(reply, btn)
                    WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply, interactive=interactive)
                    return {"status": "wallet_info", "reply": reply, "ai_classified": True, "intent": "CHECK_WALLET"}

                if ai_res.intent == "MUNICIPAL_NOTICES":
                    reply = strings.get("municipal_notices", strings.get("notices_unavailable"))
                    btn = [("MENU_MAIN", "मुख्य मेनू" if lang == "mr" else "Main Menu")]
                    interactive = WhatsAppService.build_quick_buttons_interactive(reply, btn)
                    WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply, interactive=interactive)
                    return {"status": "municipal_notices", "reply": reply, "ai_classified": True, "intent": "MUNICIPAL_NOTICES"}

                if ai_res.intent == "REGISTER_EVENT":
                    citizen.conversation_state = "AWAITING_EVENT_CATEGORY"
                    citizen.pending_complaint_data = json.dumps({"flow": "event"})
                    db.commit()
                    reply = strings["event_category_prompt"]
                    cat_list = WhatsAppService.build_event_categories_interactive(lang)
                    WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply, interactive=cat_list)
                    return {"status": "awaiting_event_category", "reply": reply, "ai_classified": True, "intent": "REGISTER_EVENT"}

                if ai_res.intent == "GRATITUDE":
                    reply = strings.get("thank_you", "Thank you! / धन्यवाद!")
                    btn = [("MENU_MAIN", "मुख्य मेनू" if lang == "mr" else "Main Menu")]
                    interactive = WhatsAppService.build_quick_buttons_interactive(reply, btn)
                    WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply, interactive=interactive)
                    return {"status": "gratitude_acknowledged", "reply": reply, "ai_classified": True, "intent": "GRATITUDE"}

                if ai_res.intent == "HELP":
                    reply = strings["help_text"]
                    btn = [("MENU_MAIN", "मुख्य मेनू" if lang == "mr" else "Main Menu")]
                    interactive = WhatsAppService.build_quick_buttons_interactive(reply, btn)
                    WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply, interactive=interactive)
                    return {"status": "help", "reply": reply, "ai_classified": True, "intent": "HELP"}

                if ai_res.intent == "OPEN_MENU":
                    full_menu_text = WhatsAppService.build_full_menu_text(citizen, db, lang=lang)
                    interactive_btns = WhatsAppService.build_primary_buttons_interactive(
                        lang=lang,
                        body_text=full_menu_text
                    )
                    WhatsAppService.send_meta_whatsapp(
                        citizen.phone_number,
                        message_text=full_menu_text,
                        interactive=interactive_btns
                    )
                    return {"status": "full_menu_presented", "reply": full_menu_text, "ai_classified": True, "intent": "OPEN_MENU"}

                if ai_res.intent == "CHANGE_LANGUAGE":
                    if ai_res.target_language in {"en", "mr"}:
                        new_lang = ai_res.target_language
                        citizen.preferred_language = new_lang
                        db.commit()
                        all_texts = _build_texts()
                        strings = all_texts[new_lang]
                        reply = strings.get("language_changed", (
                            "Language changed to English 🇬🇧\n\n"
                            if new_lang == "en"
                            else "भाषा मराठी म्हणून सेट केली आहे 🇮🇳\n\n"
                        )) + strings["help_text"]
                        btn = [("MENU_MAIN", "Main Menu" if new_lang == "en" else "मुख्य मेनू")]
                        interactive = WhatsAppService.build_quick_buttons_interactive(reply, btn)
                        WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply, interactive=interactive)
                        return {"status": "help", "reply": reply, "ai_classified": True, "intent": "CHANGE_LANGUAGE", "language": new_lang}
                    else:
                        citizen.conversation_state = "AWAITING_LANGUAGE"
                        db.commit()
                        prompt_text = WhatsAppTemplates.build_language_selection_prompt(lang)
                        lang_sel = WhatsAppService.build_language_selection_interactive(body_text=prompt_text)
                        WhatsAppService.send_meta_whatsapp(citizen.phone_number, prompt_text, interactive=lang_sel)
                        return {"status": "awaiting_language", "reply": prompt_text, "ai_classified": True, "intent": "CHANGE_LANGUAGE"}

                if ai_res.intent == "MUNICIPAL_FAQ":
                    reply = (ai_res.contextual_reply or "").strip()
                    if not reply:
                        reply = strings["help_text"]
                    primary_btns = WhatsAppService.build_primary_buttons_interactive(lang=lang, body_text=reply)
                    WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply, interactive=primary_btns)
                    return {"status": "faq_answered", "reply": reply, "ai_classified": True, "intent": "MUNICIPAL_FAQ"}

                if ai_res.intent == "UNCLEAR":
                    reply = (ai_res.contextual_reply or "").strip()
                    if not reply:
                        reply = (
                            "आपला संदेश स्पष्ट समजला नाही. आपण खालील पर्यायांमधून निवड करू शकता:"
                            if lang == "mr"
                            else "I couldn't quite understand your request. You can choose from the options below:"
                        )
                    primary_btns = WhatsAppService.build_primary_buttons_interactive(lang=lang, body_text=reply)
                    WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply, interactive=primary_btns)
                    return {"status": "unclear_clarified", "reply": reply, "ai_classified": True, "intent": "UNCLEAR"}

        # Deterministic Gratitude
        if clean_text in {"GRATITUDE", "THANKS", "THANK_YOU"} or lowered in {"thank you", "thanks", "thank u", "धन्यवाद", "आभारी आहे", "shukriya"}:
            reply = strings.get("thank_you", "Thank you! / धन्यवाद!")
            btn = [("MENU_MAIN", "मुख्य मेनू" if lang == "mr" else "Main Menu")]
            interactive = WhatsAppService.build_quick_buttons_interactive(reply, btn)
            WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply, interactive=interactive)
            return {"status": "gratitude_acknowledged", "reply": reply}

        # Option 1: Report Waste
        if clean_text in {"MENU_REPORT_WASTE", "1"} or "report" in lowered or "तक्रार नोंद" in lowered:
            citizen.conversation_state = "AWAITING_PHOTO"
            db.commit()
            reply = strings["ask_photo"]
            WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
            return {"status": "awaiting_photo", "reply": reply}

        # Option 2: General Complaint
        if clean_text in {"MENU_GENERAL_COMPLAINT", "2"} or "general" in lowered or "सामान्य" in lowered:
            citizen.conversation_state = "AWAITING_GENERAL_COMPLAINT"
            db.commit()
            reply = strings["general_complaint_prompt"]
            WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
            return {"status": "awaiting_general_complaint", "reply": reply}

        # Handle AWAITING_GENERAL_COMPLAINT state — create a general complaint from free text
        if citizen.conversation_state == "AWAITING_GENERAL_COMPLAINT" and clean_text:
            citizen_user_id = citizen.user_id
            linked_user = db.query(User).filter(User.id == citizen_user_id).first() if citizen_user_id else None
            complaint_ward = WhatsAppService.authoritative_linked_citizen_ward(citizen, linked_user)
            driver_display = "नियुक्ती प्रलंबित" if lang == "mr" else "Pending Assignment"

            _state_before = citizen.conversation_state
            for _attempt in range(_WA_MAX_RETRIES):
                ticket_num = _generate_whatsapp_tracking_id(complaint_ward or "0")
                try:
                    new_complaint = Complaint(
                        tracking_number=ticket_num,
                        citizen_id=citizen_user_id,
                        whatsapp_citizen_id=citizen.id,
                        ward=complaint_ward or "Unassigned",
                        location_address="Location not provided",
                        waste_type="General Complaint",
                        description=clean_text[:500],
                        ai_status="Pending Review",
                        ai_confidence=None,
                        status="Pending",
                        assigned_driver_id=None,
                        assigned_driver_name=None
                    )
                    db.add(new_complaint)
                    db.flush()
                    citizen.conversation_state = "IDLE"
                    db.commit()
                    break
                except Exception as exc:
                    db.rollback()
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
            gen_interactive = WhatsAppService.build_quick_buttons_interactive(reply, gen_buttons)
            WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply, interactive=gen_interactive)
            return {"status": "awaiting_general_complaint", "ticket": ticket_num, "reply": reply}

        # Option 3: Garbage Truck Tracking (stub — no live GPS available)
        if clean_text in {"MENU_VEHICLE_TRACKING", "3"} or "truck" in lowered or "vehicle" in lowered or "घंटागाडी" in lowered or "गाडी" in lowered:
            reply = strings["truck_unavailable"]
            btn = [("MENU_MAIN", "मुख्य मेनू" if lang == "mr" else "Main Menu")]
            interactive = WhatsAppService.build_quick_buttons_interactive(reply, btn)
            WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply, interactive=interactive)
            return {"status": "truck_unavailable", "reply": reply}

        # Option 4: Collection Schedule (stub — not yet available)
        if clean_text in {"MENU_COLLECTION_SCHEDULE", "4"} or "schedule" in lowered or "वेळापत्रक" in lowered:
            reply = strings["schedule_unavailable"]
            btn = [("MENU_MAIN", "मुख्य मेनू" if lang == "mr" else "Main Menu")]
            interactive = WhatsAppService.build_quick_buttons_interactive(reply, btn)
            WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply, interactive=interactive)
            return {"status": "schedule_unavailable", "reply": reply}

        # Option 5: Eco Wallet
        if clean_text in {"MENU_ECO_WALLET", "5"} or "wallet" in lowered or "coin" in lowered or "वॉलेट" in lowered:
            rupees = citizen.eco_coins // 2
            reply = strings["wallet_info"].format(coins=citizen.eco_coins, rupees=rupees)
            btn = [("MENU_MAIN", "मुख्य मेनू" if lang == "mr" else "Main Menu")]
            interactive = WhatsAppService.build_quick_buttons_interactive(reply, btn)
            WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply, interactive=interactive)
            return {"status": "wallet_info", "reply": reply}

        # Option 6: My Complaints
        if clean_text in {"MENU_MY_COMPLAINTS", "6"} or "track" in lowered or "स्थिती" in lowered or "my complaint" in lowered or "माझ्या तक्रारी" in clean_text:
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
            complaint_buttons = [
                ("MENU_REPORT_WASTE", "कचरा तक्रार" if lang == "mr" else "Report Waste"),
                ("MENU_MAIN", "मुख्य मेनू" if lang == "mr" else "Main Menu")
            ]
            interactive = WhatsAppService.build_quick_buttons_interactive(reply, complaint_buttons)
            WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply, interactive=interactive)
            return {"status": "track_complaints", "reply": reply}

        # Option 7: Municipal Notices (renumbered — old option 7 was Leaderboard, now completely removed)
        if clean_text in {"MENU_NOTICES", "7"} or "notice" in lowered or "सूचना" in lowered:
            reply = strings["notices_unavailable"]
            btn = [("MENU_MAIN", "मुख्य मेनू" if lang == "mr" else "Main Menu")]
            interactive = WhatsAppService.build_quick_buttons_interactive(reply, btn)
            WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply, interactive=interactive)
            return {"status": "notices_unavailable", "reply": reply}

        # Direct Language Switch Buttons or Words
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

        # Option 8: Help & Change Language (renumbered; legacy option 9 also preserved for compatibility)
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
