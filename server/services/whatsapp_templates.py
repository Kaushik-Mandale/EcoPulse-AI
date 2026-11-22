"""
EcoPulse AI — Multilingual Response Templates
Centralized bilingual and multilingual templates for WhatsApp municipal assistant.
Provides strictly validated, localized copy for Dhule Municipal Corporation (धुळे महानगरपालिका).
"""
from typing import Optional
from server.utils.config import config


class WhatsAppTemplates:
    """Centralized registry of municipal response templates and prompt builders."""

    # Standard Language Selection Prompts
    LANGUAGE_PROMPT_EN = (
        "Welcome to EcoPulse AI! Please select your preferred language:\n\n"
        "1. English\n"
        "2. मराठी"
    )

    LANGUAGE_PROMPT_MR = (
        "इकोपल्स AI मध्ये आपले स्वागत आहे!\n\n"
        "कृपया आपली पसंतीची भाषा निवडा:\n\n"
        "1. English\n"
        "2. मराठी"
    )

    LANGUAGE_PROMPT_BILINGUAL = (
        "Welcome to EcoPulse AI / इकोपल्स AI मध्ये आपले स्वागत आहे!\n\n"
        "Choose your preferred language / कृपया भाषा निवडा:\n\n"
        "1. English\n"
        "2. मराठी"
    )

    @classmethod
    def build_language_selection_prompt(cls, lang: Optional[str] = None) -> str:
        """Returns the appropriate language selection prompt based on detected context."""
        if lang == "mr":
            return cls.LANGUAGE_PROMPT_MR
        if lang == "en":
            return cls.LANGUAGE_PROMPT_EN
        return cls.LANGUAGE_PROMPT_BILINGUAL

    @staticmethod
    def build_all_texts() -> dict:
        """
        Builds and returns the comprehensive bilingual string dictionary used across
        the WhatsApp service and tests. Retains full backward compatibility with legacy keys.
        """
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
                # Onboarding & Auth
                "unauthorized": onboarding_mr,
                "not_linked_prompt": onboarding_mr,
                "language_selection_prompt": WhatsAppTemplates.LANGUAGE_PROMPT_MR,
                "language_changed": "भाषा मराठी म्हणून सेट केली आहे 🇮🇳\n\n",
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

                # Menus
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

                # Waste Reporting Flow
                "ask_photo": (
                    "📸 *कचरा तक्रार नोंदणी*\n\n"
                    "कृपया कचऱ्याचा, घाणीचा किंवा ओव्हरफ्लो झालेल्या कुंडीचा *फोटो पाठवा*."
                ),
                "photo_received_ack": (
                    "📸 *फोटो प्राप्त झाला! / Photo received!* ✅"
                ),
                "ask_location": (
                    "📍 Location Required / स्थान आवश्यक\n\n"
                    "कृपया खालील बटण दाबून कचऱ्याचे ठिकाण शेअर करा.\n"
                    "Please tap below to share the waste location.\n\n"
                    "💡 आपण पत्ता टाईप करूनही पाठवू शकता (उदा. 'पत्ता: स्टेशन रोड, धुळे') / "
                    "Or reply with an address (e.g. 'Address: Station Road, Dhule')."
                ),
                "invalid_location": (
                    "⚠️ वैध स्थान मिळाले नाही / Valid location not received.\n\n"
                    "कृपया खालील बटण दाबून अचूक GPS लोकेशन पाठवा किंवा 'पत्ता: ...' लिहून पाठवा.\n"
                    "Please tap the button below to share GPS location, or reply with 'Address: ...'."
                ),
                "report_success": (
                    "✅ *तक्रार यशस्वीरित्या नोंदवली गेली!*\n\n"
                    "🎫 *तक्रार क्र. / Ticket ID:* #{ticket}\n"
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

                # General Civic Complaint Flow
                "general_complaint_prompt": (
                    "📝 *सामान्य तक्रार*\n\n"
                    "कृपया आपली तक्रार थोडक्यात लिहा (रस्ता, पाणी, दिवे, अतिक्रमण इ.).\n"
                    "उदा: *मेन रोडवर मोठा खड्डा आहे, दुरुस्ती आवश्यक आहे.*"
                ),
                "general_complaint_received": (
                    "✅ *सामान्य तक्रार नोंदवली गेली आहे!*\n\n"
                    "📋 तक्रार क्रमांक: *{ticket}*\n"
                    "📝 तपशील: {description}\n"
                    "🚛 नियुक्त अधिकारी / कर्मचारी: *{driver}*\n\n"
                    "🎉 तक्रार नोंदवल्याबद्दल आपल्याला *+10 EcoCoins* मिळाले आहेत!\n"
                    "संबंधित विभागामार्फत लवकरच कार्यवाही केली जाईल."
                ),

                # Complaint Tracking
                "no_complaints": (
                    "🔍 आपल्या खात्याशी सध्या कोणतीही प्रलंबित तक्रार नाही. परिसर स्वच्छ आहे! 🌟"
                ),
                "complaints_header": "🔍 *आपल्या तक्रारींची सद्यस्थिती:*\n\n",

                # Driver Assignment Update
                "driver_assignment_update": (
                    "🚛 *स्वच्छता गाडी व चालक नेमणूक*\n\n"
                    "तक्रार क्र.: *#{ticket}*\n"
                    "चालक / कर्मचारी: *{driver}*\n"
                    "संपर्क: *{phone}*\n"
                    "अपेक्षित वेळ (ETA): *{eta}*"
                ),

                # Collection Schedule
                "collection_schedule": (
                    "🗓️ *धुळे महानगरपालिका कचरा संकलन वेळापत्रक*\n\n"
                    "⏰ *सकाळची फेरी:* सकाळी ७:०० ते ११:००\n"
                    "⏰ *दुपारची फेरी:* दुपारी २:०० ते ५:००\n\n"
                    "🚛 घंटागाडी दररोज आपल्या प्रभाग व गल्लीत येते.\n"
                    "💡 *महत्त्वाचे:* कृपया ओला कचरा हिरव्या डब्यात आणि सुका कचरा निळ्या डब्यात वेगळा ठेवा."
                ),
                "schedule_unavailable": (
                    "🗓️ *कचरा संकलन वेळापत्रक*\n\n"
                    "⚠️ आपल्या भागाचे डिजिटल वेळापत्रक अद्याप उपलब्ध नाही.\n"
                    "कृपया आपल्या प्रभाग कार्यालयाशी संपर्क साधा.\n\n"
                    "📞 धुळे महानगरपालिका: 0562-XXXXXX"
                ),

                # Vehicle Tracking
                "truck_unavailable": (
                    "🚛 *घंटागाडी थेट ट्रॅकिंग*\n\n"
                    "⚠️ सध्या थेट GPS ट्रॅकिंग उपलब्ध नाही.\n"
                    "कृपया आपल्या प्रभाग कार्यालयाशी संपर्क साधा किंवा नंतर पुन्हा प्रयत्न करा.\n\n"
                    "📞 धुळे महानगरपालिका हेल्पलाइन: 0562-XXXXXX"
                ),

                # EcoWallet
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

                # Municipal Notices
                "municipal_notices": (
                    "📢 *धुळे महानगरपालिका अधिकृत सूचना*\n\n"
                    "🌿 *'स्वच्छ धुळे, सुंदर धुळे' अभियान २०२६ सुरू आहे.*\n"
                    "🚯 सार्वजनिक ठिकाणी कचरा फेकल्यास दंड आकारला जाऊ शकतो.\n"
                    "♻️ ओला व सुका कचरा घंटागाडीतच द्या.\n"
                    "📞 नागरिक तक्रार निवारण कक्ष: २४ तास सुरू."
                ),
                "notices_unavailable": (
                    "📢 *धुळे महानगरपालिका सूचना*\n\n"
                    "⚠️ सध्या कोणतीही नवीन अधिकृत सूचना नाही.\n"
                    "स्वच्छता मोहीम नियमितपणे सुरू आहे. परिसर स्वच्छ ठेवा! 🌿"
                ),

                # Help & Language
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

                # Gratitude & Confirmation
                "thank_you": (
                    "🙏 *आपले मनःपूर्वक धन्यवाद!*\n\n"
                    "धुळे शहर स्वच्छ आणि सुंदर ठेवण्यासाठी आपले सहकार्य मोलाचे आहे. "
                    "आम्ही सदैव आपल्या सेवेत तत्पर आहोत. आपला दिवस शुभ जावो! 🌿"
                ),
                "confirmation": "✅ माहिती यशस्वीरित्या जतन करण्यात आली आहे.",
                "unrecognized_option": "⚠️ पर्याय उपलब्ध नाही. कृपया १ ते ८ मधील क्रमांक पाठवा किंवा खालील बटणे वापरा.",

                # Errors & Account Linking
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

                # Public Event Flow
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
                # Onboarding & Auth
                "unauthorized": onboarding_en,
                "not_linked_prompt": onboarding_en,
                "language_selection_prompt": WhatsAppTemplates.LANGUAGE_PROMPT_EN,
                "language_changed": "Language changed to English 🇬🇧\n\n",
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

                # Menus
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

                # Waste Reporting Flow
                "ask_photo": (
                    "📸 *Report Waste Complaint*\n\n"
                    "Please send a clear *photo* of the garbage, debris, or overflowing bin."
                ),
                "photo_received_ack": (
                    "📸 *Photo received! / फोटो प्राप्त झाला!* ✅"
                ),
                "ask_location": (
                    "📍 Location Required / स्थान आवश्यक\n\n"
                    "कृपया खालील बटण दाबून कचऱ्याचे ठिकाण शेअर करा.\n"
                    "Please tap below to share the waste location.\n\n"
                    "💡 You can also reply with an address (e.g. 'Address: Station Road, Dhule') / "
                    "किंवा पत्ता टाईप करा (उदा. 'पत्ता: स्टेशन रोड, धुळे')."
                ),
                "invalid_location": (
                    "⚠️ Valid location not received / वैध स्थान मिळाले नाही.\n\n"
                    "Please tap the button below to share GPS location, or reply with 'Address: ...'.\n"
                    "कृपया खालील बटण दाबून अचूक GPS लोकेशन पाठवा किंवा 'पत्ता: ...' लिहून पाठवा."
                ),
                "report_success": (
                    "✅ *Complaint Registered Successfully!*\n\n"
                    "🎫 *Ticket ID / Ticket #:* #{ticket}\n"
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

                # General Civic Complaint Flow
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

                # Complaint Tracking
                "no_complaints": (
                    "🔍 No active complaints found for your account. Everything is clean and green! 🌟"
                ),
                "complaints_header": "🔍 *Your Recent Complaints Status:*\n\n",

                # Driver Assignment Update
                "driver_assignment_update": (
                    "🚛 *Sanitation Staff & Vehicle Assignment*\n\n"
                    "Ticket #: *#{ticket}*\n"
                    "Driver / Staff: *{driver}*\n"
                    "Contact: *{phone}*\n"
                    "Estimated ETA: *{eta}*"
                ),

                # Collection Schedule
                "collection_schedule": (
                    "🗓️ *Dhule Municipal Corporation Waste Collection Schedule*\n\n"
                    "⏰ *Morning Shift:* 7:00 AM – 11:00 AM\n"
                    "⏰ *Afternoon Shift:* 2:00 PM – 5:00 PM\n\n"
                    "🚛 Garbage trucks visit every ward and street daily.\n"
                    "💡 *Important:* Please segregate wet waste into green bins and dry waste into blue bins."
                ),
                "schedule_unavailable": (
                    "🗓️ *Waste Collection Schedule*\n\n"
                    "⚠️ Digital schedule is not yet available for your specific ward.\n"
                    "Please contact your ward office for exact timings.\n\n"
                    "📞 Dhule Municipal Corporation: 0562-XXXXXX"
                ),

                # Vehicle Tracking
                "truck_unavailable": (
                    "🚛 *Live Garbage Truck Tracking*\n\n"
                    "⚠️ Real-time GPS tracking is temporarily unavailable.\n"
                    "Collection vehicles are operating on normal daily schedules.\n\n"
                    "📞 Dhule Helpline: 0562-XXXXXX"
                ),

                # EcoWallet
                "wallet_info": (
                    "🪙 *EcoWallet & Rewards (EcoCoins)*\n\n"
                    "Balance: *{coins} EcoCoins*\n"
                    "Estimated Value: *₹{rupees}*\n\n"
                    "🎁 *Rebate Options:*\n"
                    "• 50 Coins = ₹25 Property Tax Rebate\n"
                    "• 100 Coins = 1 Month Free City Library Pass\n"
                    "• 200 Coins = 2 Free Tree Saplings (Municipal Nursery)\n\n"
                    "Contact the Dhule Municipal Tax Department to redeem."
                ),

                # Municipal Notices
                "municipal_notices": (
                    "📢 *Dhule Municipal Corporation Notices*\n\n"
                    "🌿 *'Clean Dhule, Beautiful Dhule' Campaign 2026 is active.*\n"
                    "🚯 Littering in public places may attract municipal penalties.\n"
                    "♻️ Please hand over segregated waste to the garbage vehicle.\n"
                    "📞 Citizen Grievance Cell: Active 24/7."
                ),
                "notices_unavailable": (
                    "📢 *Dhule Municipal Notices*\n\n"
                    "⚠️ No active broadcast notices at this moment.\n"
                    "Cleanliness drives are running normally. Keep your surroundings clean! 🌿"
                ),

                # Help & Language
                "help_text": (
                    "❓ *Dhule Municipal Waste Helpline*\n\n"
                    "📞 Toll Free: 1800-XXX-XXXX\n"
                    "📧 Email: contact@dhulecorporation.gov.in\n"
                    "🌐 Portal: ecopulse-ai.gov.in\n\n"
                    "🌐 *Change Language:*\n"
                    "• Type 'ENGLISH' for English.\n"
                    "• Type 'MARATHI' for Marathi.\n"
                    "• Type 'EVENT' to register a public gathering."
                ),

                # Gratitude & Confirmation
                "thank_you": (
                    "🙏 *You're Very Welcome!*\n\n"
                    "Thank you for helping us keep Dhule clean and beautiful. "
                    "We are always here to assist you. Have a wonderful day! 🌿"
                ),
                "confirmation": "✅ Information has been saved successfully.",
                "unrecognized_option": "⚠️ Unrecognized option. Please reply with a number from 1 to 8 or tap the buttons below.",

                # Errors & Account Linking
                "image_error": "⚠️ Could not accept image. Please send a clear JPEG, PNG, or WebP photo.",
                "link_prompt": (
                    "🔗 *Link WhatsApp Account*\n\n"
                    "Send the verification code from your Citizen Portal in this format:\n\n"
                    "LINK <code>\n\n"
                    "Example: LINK 123456"
                ),
                "link_invalid": (
                    "❌ *Code invalid or expired.*\n\n"
                    "Please log in to the EcoPulse website and generate a new code:\n"
                    f"🌐 {frontend_url}"
                ),

                # Public Event Flow
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
                    "Please send the event venue location pin or type 'ADDRESS: ...'.\n"
                    "कृपया कार्यक्रमाच्या जागेचे Location Pin पाठवा किंवा पत्ता पाठवा (उदा. 'पत्ता: साक्री रोड, धुळे')."
                ),
                "event_summary": (
                    "📋 *Event Summary / सार्वजनिक कार्यक्रम नोंदणी सारांश*\n\n"
                    "🎉 Category: {category}\n"
                    "📅 Date: {date}\n"
                    "⏰ Time: {time}\n"
                    "📍 Location: {location}\n\n"
                    "Please review and reply 'Confirm' to submit or 'Cancel' to abort."
                ),
                "event_success": (
                    "✅ *Public Event Registered Successfully!*\n\n"
                    "🎫 Reference ID: *{ref_id}*\n"
                    "📅 Date: {date} | ⏰ Time: {time}\n"
                    "📍 Venue: {location}\n\n"
                    "Municipal sanitation teams have been scheduled for proactive collection. Thank you! 🌱"
                ),
                "event_cancelled": "❌ Event reporting cancelled / कार्यक्रम नोंदणी रद्द करण्यात आली आहे."
            }
        }


def build_response_templates() -> dict:
    """Convenience helper returning centralized response templates."""
    return WhatsAppTemplates.build_all_texts()
