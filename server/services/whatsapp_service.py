import json
import logging
import random
import re
import hashlib
import httpx
from typing import Optional
from sqlalchemy.orm import Session
from server.utils.config import config
from server.models.whatsapp_session import WhatsAppCitizen
from server.models.complaint import Complaint
from server.models.task import DriverTask
from server.models.user import User
from server.services.media_storage import get_media_storage

logger = logging.getLogger(__name__)


class MediaValidationError(Exception):
    """Raised when an incoming WhatsApp media fails validation rules."""
    pass


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


# Bilingual UI Strings for Shirpur Municipal Council
TEXTS = {
    "mr": {
        "unauthorized": (
            "🏛️ *शिरपूर नगरपरिषद ईको-पल्स (EcoPulse AI)*\n\n"
            "नमस्कार! हे डिजिटल स्वच्छता पोर्टल फक्त शिरपूर नगरपरिषदेच्या अधिकृत रहिवाशांसाठी आहे.\n\n"
            "🔐 *प्रवेश कसा मिळवाल?*\n"
            "आपल्या घरावर किंवा कचऱ्याच्या डब्यावरील QR कोड स्कॅन करा किंवा खालीलप्रमाणे मेसेज पाठवा:\n"
            "उदा: *JOIN SHP-W12-H1042*\n"
            "(प्रभाग क्रमांक व घर क्रमांक)"
        ),
        "authorized_welcome": (
            "🏛️ *शिरपूर नगरपरिषद - ईको-पल्स नागरिक कक्ष*\n\n"
            "नमस्कार {name}!\n"
            "📍 प्रभाग: *{ward}* | घर क्र.: *{house}*\n"
            "✅ आपले घर प्रमाणित करण्यात आले आहे.\n\n"
            "🪙 *ईको-कॉइन्स बॅलन्स: {coins} गुण (₹{rupees} कर सवलत)*\n\n"
            "कृपया खालीलपैकी पर्याय निवडा:"
        ),
        "menu_options": (
            "1️⃣ *कचरा तक्रार नोंदवा* (फोटो व लोकेशन पाठवा)\n"
            "2️⃣ *माझ्या तक्रारी तपासा* (स्थिती व ड्रायव्हर)\n"
            "3️⃣ *ईको-वॉलेट आणि रिवॉर्ड्स* (कर सवलत / फायदे)\n"
            "4️⃣ *घंटागाडी लाईव्ह ट्रॅकिंग* (गाडी कुठे आहे?)\n"
            "5️⃣ *महानगरपालिका सूचना*\n"
            "6️⃣ *भाषा बदला (Switch to English)*\n\n"
            "👉 *पर्याय क्रमांक (1-6) पाठवा किंवा थेट फोटो पाठवा.*"
        ),
        "ask_photo": (
            "📸 *कचरा तक्रार नोंदणी*\n\n"
            "कृपया कचऱ्याचा, घाणीचा किंवा ओव्हरफ्लो झालेल्या कुंडीचा *फोटो पाठवा*."
        ),
        "ask_location": (
            "📍 *फोटो प्राप्त झाला!*\n\n"
            "आता कृपया खालील अटॅचमेंट चिन्हावर क्लिक करून *WhatsApp Location (आपले सध्याचे स्थान)* पाठवा."
        ),
        "report_success": (
            "✅ *तक्रार यशस्वीरित्या नोंदवली गेली!*\n\n"
            "🎫 *तक्रार क्र.:* #{ticket}\n"
            "📍 *प्रभाग:* {ward}\n"
            "🚛 *नियुक्त गाडी:* {driver}\n"
            "⏱️ *निराकरण कालावधी:* ४ तासांच्या आत\n\n"
            "🎉 *अभिनंदन!* शहर स्वच्छ ठेवण्यासाठी आपल्याला *+20 ईको-कॉइन्स* मिळाले आहेत!\n"
            "एकूण शिल्लक: *{coins} गुण*."
        ),
        "no_complaints": (
            "🔍 आपल्या प्रभागात सध्या कोणतीही प्रलंबित तक्रार नाही. परिसर स्वच्छ आहे! 🌟"
        ),
        "complaints_header": "🔍 *आपल्या तक्रारींची सद्यस्थिती:*\n\n",
        "wallet_info": (
            "🪙 *शिरपूर ईको-वॉलेट (EcoCoin Wallet)*\n\n"
            "शिल्लक गुण: *{coins} EcoCoins*\n"
            "अंदाजे मूल्य: *₹{rupees}*\n\n"
            "🎁 *सवलत पर्याय:*\n"
            "• ५० कॉइन्स = ₹२५ घरपट्टी (Property Tax) सवलत\n"
            "• १०० कॉइन्स = १ महिना शिरपूर मोफत वाचनालय पास\n"
            "• २०० कॉइन्स = २ मोफत फळझाडे रोपे (नगरपरिषद नर्सरी)\n\n"
            "अधिक माहितीसाठी नगरपरिषद कर कक्षाशी संपर्क साधा."
        ),
        "truck_tracking": (
            "🚛 *घंटागाडी थेट ट्रॅकिंग - {ward}*\n\n"
            "चालक: *सुनील पाटील* (मो. ९८२३० ९९१२४)\n"
            "वाहन क्रमांक: *MH-18-BZ-4412*\n"
            "सध्याचे स्थान: *महावीर चौक, मेन रोड* (सुमारे ४०० मीटर)\n"
            "आपल्या भागात पोहोचण्याची वेळ: *सुमारे १० ते १५ मिनिटे*\n\n"
            "🔔 कृपया ओला व सुका कचरा वेगळा ठेवा."
        ),
        "notices": (
            "📢 *शिरपूर नगरपरिषद अधिकृत सूचना*\n\n"
            "१. प्रत्येक मंगळवारी व शुक्रवारी फक्त ई-कचरा व सुका कचरा संकलन.\n"
            "२. प्लास्टिक बंदी नियमांचे काटेकोर पालन करा.\n"
            "३. पाणी पुरवठा वेळ: सकाळी ६:३० ते ८:००."
        ),
        "lang_switched": "✅ भाषा बदलून मराठी करण्यात आली आहे.",
        "image_error": (
            "⚠️ *फोटो स्वीकारला नाही.*\n\n"
            "कृपया स्पष्ट JPEG, PNG किंवा WebP स्वरूपातील फोटो पाठवा (कमाल १० MB)."
        )
    },
    "en": {
        "unauthorized": (
            "🏛️ *Shirpur Municipal Council EcoPulse AI*\n\n"
            "Welcome! This civic sanitation portal is exclusively for authorized residents of Shirpur.\n\n"
            "🔐 *How to Get Access?*\n"
            "Scan the EcoPulse QR code on your gate/bin or send:\n"
            "*JOIN SHP-W12-H1042*\n"
            "(Ward Number & Household ID)"
        ),
        "authorized_welcome": (
            "🏛️ *Shirpur Municipal Council - Citizen Desk*\n\n"
            "Welcome {name}!\n"
            "📍 Ward: *{ward}* | Household: *{house}*\n"
            "✅ Your household is authorized.\n\n"
            "🪙 *EcoCoin Balance: {coins} pts (₹{rupees} rebate)*\n\n"
            "Please choose an option below:"
        ),
        "menu_options": (
            "1️⃣ *Report Waste* (Send Photo & Location)\n"
            "2️⃣ *Track Complaints* (Live status & Driver)\n"
            "3️⃣ *Eco-Wallet & Rewards* (Tax Rebates)\n"
            "4️⃣ *Live Garbage Truck* (Where is my truck?)\n"
            "5️⃣ *Municipal Notices*\n"
            "6️⃣ *भाषा बदला (Switch to Marathi)*\n\n"
            "👉 *Reply with number (1-6) or send a photo directly.*"
        ),
        "ask_photo": (
            "📸 *Report Waste Incident*\n\n"
            "Please capture and *send a photo* of the garbage accumulation or overflowing bin."
        ),
        "ask_location": (
            "📍 *Photo Received!*\n\n"
            "Now click the (+) attachment icon and share your *WhatsApp Location*."
        ),
        "report_success": (
            "✅ *Complaint Logged Successfully!*\n\n"
            "🎫 *Ticket ID:* #{ticket}\n"
            "📍 *Ward:* {ward}\n"
            "🚛 *Assigned Vehicle:* {driver}\n"
            "⏱️ *Resolution SLA:* Under 4 hours\n\n"
            "🎉 *Reward:* You earned *+20 EcoCoins* for keeping Shirpur clean!\n"
            "Current Balance: *{coins} pts*."
        ),
        "no_complaints": (
            "🔍 No active complaints found for your household. Your area is clean! 🌟"
        ),
        "complaints_header": "🔍 *Your Active Complaints:*\n\n",
        "wallet_info": (
            "🪙 *Shirpur Municipal Eco-Wallet*\n\n"
            "Balance: *{coins} EcoCoins*\n"
            "Estimated Value: *₹{rupees}*\n\n"
            "🎁 *Redemption Catalog:*\n"
            "• 50 Coins = ₹25 Property Tax Rebate\n"
            "• 100 Coins = 1-Month Library Reading Pass\n"
            "• 200 Coins = 2 Free Fruit Plant Saplings\n\n"
            "Contact Shirpur Municipal Tax Department to claim."
        ),
        "truck_tracking": (
            "🚛 *Garbage Collection Truck - {ward}*\n\n"
            "Driver: *Sunil Patil* (Ph: +91 98230 99124)\n"
            "Vehicle: *MH-18-BZ-4412*\n"
            "Current Location: *Mahavir Chowk, Main Road* (~400m away)\n"
            "Estimated Arrival: *10 to 15 minutes*\n\n"
            "🔔 Please segregate wet and dry waste."
        ),
        "notices": (
            "📢 *Official Shirpur Municipal Announcements*\n\n"
            "1. Dry & E-waste special pickup every Tuesday & Friday.\n"
            "2. Strict single-use plastic ban in effect across all 27 wards.\n"
            "3. Morning water supply schedule: 6:30 AM - 8:00 AM."
        ),
        "lang_switched": "✅ Language switched to English.",
        "image_error": (
            "⚠️ *Could not process photo.*\n\n"
            "Please send a clear photo in JPEG, PNG, or WebP format (max 10 MB)."
        )
    }
}

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
                full_name="Shirpur Resident",
                ward="Ward 12",
                household_id=None,
                is_authorized=False,
                preferred_language="mr",
                eco_coins=100,
                conversation_state="IDLE"
            )
            db.add(citizen)
            db.commit()
            db.refresh(citizen)
        return citizen

    @staticmethod
    def find_matching_citizen_user(db: Session, sender_phone: str) -> Optional[User]:
        """
        Finds a registered Citizen User with a normalized phone number match.
        Returns the User if exactly ONE unambiguous match is found.
        Returns None if 0 matches (guest-citizen flow) or if multiple matches exist (ambiguity safety).
        """
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

        # Reject any matched record whose phone is empty, whitespace, or not in candidate_phones
        valid_matches = [
            u for u in matches
            if u.phone and u.phone.strip() and u.phone in candidate_phones
        ]

        if len(valid_matches) == 1:
            return valid_matches[0]
        elif len(valid_matches) > 1:
            logger.warning(
                f"[WHATSAPP IDENTITY] Ambiguous match: {len(valid_matches)} citizen accounts found for phone {sender_phone}"
            )
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
            logger.info(f"[MOCK META WHATSAPP] To: {to_phone} | Msg: {message_text[:80]}...")
            return {"status": "simulated", "recipient": to_phone}

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
                return res.json()
        except Exception as e:
            logger.error(f"Error sending Meta WhatsApp message: {e}")
            return {"error": str(e)}

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
            logger.warning(f"[META MEDIA] WHATSAPP_TOKEN is not configured; cannot retrieve media_id={media_id}")
            return {"success": False, "error": "WHATSAPP_TOKEN is not configured"}

        if not media_id or not str(media_id).strip():
            return {"success": False, "error": "Invalid media_id"}

        meta_url = f"https://graph.facebook.com/{api_version}/{media_id}"
        headers = {"Authorization": f"Bearer {token}"}

        try:
            with httpx.Client(timeout=15.0) as client:
                # Step 1: Request metadata from Meta Graph API
                meta_res = client.get(meta_url, headers=headers)
                if meta_res.status_code != 200:
                    logger.error(f"[META MEDIA] Metadata request failed for media_id={media_id} (status: {meta_res.status_code})")
                    return {"success": False, "error": f"Meta metadata request failed with HTTP {meta_res.status_code}"}

                try:
                    meta_data = meta_res.json()
                except Exception:
                    logger.error(f"[META MEDIA] Invalid JSON response from Meta for media_id={media_id}")
                    return {"success": False, "error": "Invalid metadata response from Meta"}

                download_url = meta_data.get("url")
                if not download_url:
                    logger.error(f"[META MEDIA] No download URL returned for media_id={media_id}")
                    return {"success": False, "error": "No download URL returned by Meta"}

                declared_mime = meta_data.get("mime_type")

                # Step 2: Download raw binary from returned download URL using Bearer token
                bin_res = client.get(download_url, headers=headers)
                if bin_res.status_code != 200:
                    logger.error(f"[META MEDIA] Binary download failed for media_id={media_id} (status: {bin_res.status_code})")
                    return {"success": False, "error": f"Media binary download failed with HTTP {bin_res.status_code}"}

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

            logger.info(f"[META MEDIA] Successfully retrieved, validated, and stored media_id={media_id} (size: {len(content)} bytes)")
            return {
                "success": True,
                "storage_ref": storage_ref,
                "mime_type": detected_mime,
                "sha256": calc_sha256,
                "file_size": len(content),
                "media_id": media_id
            }

        except MediaValidationError as e:
            logger.warning(f"[META MEDIA] Validation rejected media_id={media_id}: {str(e)}")
            return {"success": False, "error": str(e)}
        except httpx.TimeoutException:
            logger.error(f"[META MEDIA] Request timed out while retrieving media_id={media_id}")
            return {"success": False, "error": "Connection timed out contacting Meta Graph API"}
        except Exception as e:
            logger.error(f"[META MEDIA] Unexpected failure handling media_id={media_id}: {type(e).__name__}")
            return {"success": False, "error": "Internal error processing media binary"}

    @staticmethod
    def handle_incoming_message(
        db: Session,
        sender_phone: str,
        message_type: str,
        text_body: str = "",
        media_url: str = "",
        media_id: str = "",
        latitude: float = None,
        longitude: float = None
    ) -> dict:
        """Central message handling engine for WhatsApp."""
        citizen = WhatsAppService.get_or_create_citizen(db, sender_phone)
        lang = citizen.preferred_language or "mr"
        strings = TEXTS.get(lang, TEXTS["mr"])
        clean_text = (text_body or "").strip()

        # ----------------------------------------------------
        # 1. Household QR Code Registration (e.g. JOIN SHP-W12-H1042)
        # ----------------------------------------------------
        qr_match = re.search(r'(?:JOIN\s+)?(SHP[-_]W(\d+)[-_]H([A-Za-z0-9]+))', clean_text, re.IGNORECASE)
        if qr_match:
            full_code = qr_match.group(1).upper()
            ward_num = qr_match.group(2)
            citizen.household_id = full_code
            citizen.ward = f"Ward {ward_num}"
            citizen.is_authorized = True
            citizen.conversation_state = "IDLE"
            db.commit()

            reply = strings["authorized_welcome"].format(
                name=citizen.full_name,
                ward=citizen.ward,
                house=citizen.household_id,
                coins=citizen.eco_coins,
                rupees=citizen.eco_coins // 2
            ) + "\n\n" + strings["menu_options"]

            WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
            return {"status": "authorized", "citizen": citizen.phone_number, "reply": reply}

        # ----------------------------------------------------
        # 2. Gatekeeper: Unauthorized Users Must Provide QR Code
        # ----------------------------------------------------
        if not citizen.is_authorized:
            reply = strings["unauthorized"]
            WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
            return {"status": "unauthorized_prompt", "reply": reply}

        # ----------------------------------------------------
        # 3. Multi-Step Reporting State Machine: Photo Ingestion
        # ----------------------------------------------------
        if message_type == "image" or "http" in media_url or media_id:
            if media_id:
                media_res = WhatsAppService.fetch_and_store_meta_media(media_id)
                if not media_res.get("success"):
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

        # ----------------------------------------------------
        # 4. Multi-Step Reporting State Machine: Location Pin Ingestion
        # ----------------------------------------------------
        if message_type == "location" or (latitude is not None and longitude is not None):
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

            # Generate formatted Shirpur ticket
            ticket_num = f"SHP-2026-W{citizen.ward.replace('Ward ', '')}-{random.randint(1000, 9999)}"
            lat_val = latitude if latitude is not None else 21.3487
            lng_val = longitude if longitude is not None else 74.8812

            # Resolve matching registered citizen User (if unambiguous phone match exists)
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

            # Persist complaint in main municipal database atomically with driver task and coin updates
            try:
                new_complaint = Complaint(
                    tracking_number=ticket_num,
                    citizen_id=citizen_user_id,
                    ward=citizen.ward,
                    location_address=f"{citizen.ward}, Shirpur (Geotagged via WhatsApp)",
                    latitude=lat_val,
                    longitude=lng_val,
                    waste_type=waste_type,
                    description=f"Reported by authorized household {citizen.household_id} via WhatsApp.",
                    image_url=image_url,
                    ai_status="Verified",
                    ai_confidence=0.96,
                    status="Pending",
                    assigned_driver_id=assigned_driver_id,
                    assigned_driver_name=assigned_driver_name
                )
                db.add(new_complaint)
                db.flush()

                # Auto-assign driver task in tasks table
                new_task = DriverTask(
                    driver_id=assigned_driver_id,
                    complaint_id=new_complaint.id,
                    location_name=new_complaint.location_address,
                    status="Pending",
                    route_order=1
                )
                db.add(new_task)

                # Award citizen +20 EcoCoins
                citizen.eco_coins += 20
                if citizen_user:
                    citizen_user.eco_coins = (citizen_user.eco_coins or 100) + 20
                citizen.conversation_state = "IDLE"
                citizen.pending_complaint_data = None
                db.commit()
            except Exception as e:
                db.rollback()
                logger.error(f"[WHATSAPP COMPLAINT] Failed to atomically persist complaint and task: {e}")
                raise

            reply = strings["report_success"].format(
                ticket=ticket_num,
                ward=citizen.ward,
                driver=driver_display,
                coins=citizen.eco_coins
            )
            WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
            return {"status": "complaint_created", "ticket": ticket_num, "reply": reply}

        # ----------------------------------------------------
        # 5. Dashboard Menu Selection Routing
        # ----------------------------------------------------
        lowered = clean_text.lower()

        # Option 1: Report Waste
        if clean_text == "1" or "report" in lowered or "तक्रार" in lowered:
            citizen.conversation_state = "AWAITING_PHOTO"
            db.commit()
            reply = strings["ask_photo"]
            WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
            return {"status": "awaiting_photo", "reply": reply}

        # Option 2: Track Complaints
        if clean_text == "2" or "track" in lowered or "स्थिती" in lowered:
            complaints = db.query(Complaint).filter(Complaint.ward == citizen.ward).order_by(Complaint.id.desc()).limit(3).all()
            if not complaints:
                reply = strings["no_complaints"]
            else:
                lines = [strings["complaints_header"]]
                for c in complaints:
                    status_icon = "⏳" if c.status == "Pending" else ("🚚" if c.status == "In Progress" else "✅")
                    lines.append(f"{status_icon} *#{c.tracking_number}*\nप्रकार: {c.waste_type}\nस्थिती: *{c.status}*\nचालक: {c.assigned_driver_name or 'नियुक्त केला जात आहे'}\n")
                reply = "\n".join(lines)
            WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
            return {"status": "track_complaints", "reply": reply}

        # Option 3: Eco Wallet
        if clean_text == "3" or "wallet" in lowered or "coin" in lowered or "वॉलेट" in lowered:
            reply = strings["wallet_info"].format(
                coins=citizen.eco_coins,
                rupees=citizen.eco_coins // 2
            )
            WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
            return {"status": "wallet_info", "reply": reply}

        # Option 4: Live Garbage Truck Tracking
        if clean_text == "4" or "truck" in lowered or "गाडी" in lowered:
            reply = strings["truck_tracking"].format(ward=citizen.ward)
            WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
            return {"status": "truck_tracking", "reply": reply}

        # Option 5: Municipal Notices
        if clean_text == "5" or "notice" in lowered or "सूचना" in lowered:
            reply = strings["notices"]
            WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
            return {"status": "notices", "reply": reply}

        # Option 6: Change Language
        if clean_text == "6" or "lang" in lowered or "भाषा" in lowered or "english" in lowered:
            new_lang = "en" if citizen.preferred_language == "mr" else "mr"
            citizen.preferred_language = new_lang
            db.commit()
            new_strings = TEXTS[new_lang]
            reply = new_strings["lang_switched"] + "\n\n" + new_strings["menu_options"]
            WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
            return {"status": "lang_switched", "language": new_lang, "reply": reply}

        # Default Fallback: Present Dashboard Menu
        reply = strings["authorized_welcome"].format(
            name=citizen.full_name,
            ward=citizen.ward,
            house=citizen.household_id or 'SHP-W12',
            coins=citizen.eco_coins,
            rupees=citizen.eco_coins // 2
        ) + "\n\n" + strings["menu_options"]
        WhatsAppService.send_meta_whatsapp(citizen.phone_number, reply)
        return {"status": "menu_presented", "reply": reply}
