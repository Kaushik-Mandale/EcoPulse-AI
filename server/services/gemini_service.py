import json
import logging
import re
from typing import Optional, Literal
from pydantic import BaseModel, Field
import httpx

from server.utils.config import config

logger = logging.getLogger(__name__)

# Allowed initial intent categories as specified by Phase 1 & 2 requirements
SUPPORTED_INTENTS = {
    "REPORT_WASTE",
    "GARBAGE_NOT_COLLECTED",
    "GENERAL_COMPLAINT",
    "TRACK_COMPLAINT",
    "COLLECTION_SCHEDULE",
    "TRACK_VEHICLE",
    "CHECK_WALLET",
    "MUNICIPAL_NOTICES",
    "REGISTER_EVENT",
    "GRATITUDE",
    "GREETING",
    "OPEN_MENU",
    "CHANGE_LANGUAGE",
    "HELP",
    "MUNICIPAL_FAQ",
    "UNCLEAR",
}


class GeminiIntentResult(BaseModel):
    """Structured representation of Gemini intent classification and response."""
    intent: Optional[Literal[
        "REPORT_WASTE",
        "GARBAGE_NOT_COLLECTED",
        "GENERAL_COMPLAINT",
        "TRACK_COMPLAINT",
        "COLLECTION_SCHEDULE",
        "TRACK_VEHICLE",
        "CHECK_WALLET",
        "MUNICIPAL_NOTICES",
        "REGISTER_EVENT",
        "GRATITUDE",
        "GREETING",
        "OPEN_MENU",
        "CHANGE_LANGUAGE",
        "HELP",
        "MUNICIPAL_FAQ",
        "UNCLEAR"
    ]] = None
    confidence: float = 0.0
    detected_language: Optional[str] = None
    target_language: Optional[str] = None  # "mr" or "en" when intent is CHANGE_LANGUAGE
    ticket_id: Optional[str] = None         # Tracking ID if extracted from message
    contextual_reply: Optional[str] = None  # Grounded answer for MUNICIPAL_FAQ or UNCLEAR
    is_fallback: bool = False
    error: Optional[str] = None


class GeminiService:
    """Service for Gemini conversational intelligence, intent classification, and civic FAQ."""

    SYSTEM_PROMPT = (
        "You are EcoPulse AI, the civic sanitation and municipal services assistant for Dhule Municipal "
        "Corporation (धुळे महानगरपालिका), Maharashtra, India.\n\n"
        "Analyze the citizen's WhatsApp message and output a strict JSON object with these fields:\n"
        "1. \"intent\": exactly one of:\n"
        "   - \"REPORT_WASTE\": citizen wants to report garbage, uncollected waste, trash, debris, or overflowing bin (e.g. 'I want to report garbage', 'कचरा उचलला नाही', 'येथे घाण साचली आहे', 'kachra pada hai').\n"
        "   - \"GARBAGE_NOT_COLLECTED\": citizen specifically complains that garbage was not picked up or collected (e.g. 'कचरा अजून उचलला नाही', 'garbage has not been picked up').\n"
        "   - \"GENERAL_COMPLAINT\": citizen reports non-waste municipal issues like streetlights, potholes, drainage, or water supply (e.g. 'मला तक्रार करायची आहे', 'street light broken', 'drainage leakage').\n"
        "   - \"TRACK_COMPLAINT\": citizen wants to check complaint status or track tickets (e.g. 'Where is my complaint?', 'माझी तक्रार कुठे आहे?', 'track my complaint').\n"
        "   - \"COLLECTION_SCHEDULE\": citizen asks about garbage collection timings or truck schedule (e.g. 'उद्या कचरा कधी येणार?', 'when does the truck arrive?', 'pickup timings').\n"
        "   - \"TRACK_VEHICLE\": citizen asks for live truck/ghantagadi location (e.g. 'घंटागाडी कुठे आहे?', 'where is the truck?', 'live tracking').\n"
        "   - \"CHECK_WALLET\": citizen asks about EcoCoins, points, or tax rebate balance (e.g. 'माझे कॉइन्स किती आहेत?', 'check my wallet', 'ecocoin balance').\n"
        "   - \"MUNICIPAL_NOTICES\": citizen asks for municipal notices, news, or announcements (e.g. 'काही नवीन सूचना आहेत का?', 'municipal notices').\n"
        "   - \"REGISTER_EVENT\": citizen wants to register a public gathering, festival, or event for bulk sanitation (e.g. 'कार्यक्रमाची नोंदणी करायची आहे', 'register event').\n"
        "   - \"GRATITUDE\": citizen expresses thanks, appreciation, or blessing (e.g. 'Thank you', 'धन्यवाद', 'आभारी आहे', 'thanks a lot', 'shukriya').\n"
        "   - \"GREETING\": citizen says hello, hi, hey, namaskar, namaste, start (e.g. 'Hello', 'Hi', 'नमस्कार', 'नमस्ते', 'Hey').\n"
        "   - \"OPEN_MENU\": citizen asks to see the menu, services list, or all options (e.g. 'सर्व पर्याय दाखवा', 'menu', 'full menu', 'show options').\n"
        "   - \"CHANGE_LANGUAGE\": citizen asks to change or switch language (e.g. 'Can I change my language?', 'मला भाषा बदलायची आहे', 'speak in English', 'मराठीत बोला').\n"
        "   - \"HELP\": citizen asks for helpline, contact details, or support assistance (e.g. 'मदत हवी आहे', 'helpline number', 'support contact').\n"
        "   - \"MUNICIPAL_FAQ\": citizen asks an informational question about Dhule municipal rules, tax rebate rates, waste segregation, or civic procedures.\n"
        "   - \"UNCLEAR\": message is ambiguous, random, or not understood.\n\n"
        "2. \"confidence\": float between 0.0 and 1.0.\n"
        "3. \"detected_language\": \"mr\", \"en\", \"hi\", or \"mixed\".\n"
        "4. \"target_language\": \"mr\" or \"en\" if intent is CHANGE_LANGUAGE and user specified target, else null.\n"
        "5. \"ticket_id\": complaint tracking number if present (e.g. DHL-2026-W12-XYZ), else null.\n"
        "6. \"contextual_reply\": \n"
        "   - For MUNICIPAL_FAQ: provide a concise, factual 1-3 sentence civic answer in the citizen's preferred language.\n"
        "   - For UNCLEAR: provide a polite 1-2 sentence clarification in the citizen's preferred language.\n"
        "   - For other intents: null (EcoPulse AI deterministic backend handles formatting).\n\n"
        "Context for Dhule Municipality (धुळे महानगरपालिका):\n"
        "- Wet waste (ओला कचरा) in green bin; dry waste (सुका कचरा) in blue bin.\n"
        "- Citizen helpline: 1800-XXX-XXXX, email: contact@dhulecorporation.gov.in.\n"
        "- EcoCoins: 50 coins = ₹25 property tax rebate, 100 coins = 1-month library pass, 200 coins = 2 nursery saplings.\n"
        "- Online Citizen Portal: https://ecopulse-ai-frontend.onrender.com/\n\n"
        "Always respond with ONLY valid raw JSON."
    )

    @staticmethod
    def _sanitize_error_message(err_str: str) -> str:
        """Strip sensitive credentials like API keys from logs or exception strings."""
        if not err_str:
            return ""
        sanitized = str(err_str)
        # Redact configured API key if present
        api_key = getattr(config, "GEMINI_API_KEY", "")
        if api_key and len(str(api_key).strip()) >= 5:
            sanitized = sanitized.replace(str(api_key).strip(), "[REDACTED]")
        # Redact query string key parameter (?key=... or &key=...)
        sanitized = re.sub(r'([?&]key=)[^&\s\'"<>]+', r'\1[REDACTED]', sanitized)
        # Redact Google API key format (AIzaSy...)
        sanitized = re.sub(r'\bAIza[0-9A-Za-z\-_]{35}\b', '[REDACTED]', sanitized)
        # Redact Authorization Bearer token if present
        sanitized = re.sub(r'(Bearer\s+)[A-Za-z0-9\-._~+/]+=*', r'\1[REDACTED]', sanitized, flags=re.IGNORECASE)
        # Redact x-goog-api-key header if present in logs
        sanitized = re.sub(r'(x-goog-api-key[:=]\s*)[^\s,;\'"]+', r'\1[REDACTED]', sanitized, flags=re.IGNORECASE)
        return sanitized

    @staticmethod
    def clean_json_text(raw_text: str) -> str:
        """Remove markdown code blocks or wrapping whitespace from model output."""
        cleaned = (raw_text or "").strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r'\s*```$', '', cleaned)
        return cleaned.strip()

    @staticmethod
    def parse_gemini_payload(data: dict) -> GeminiIntentResult:
        """Parse the raw response dict from Google Generative Language API into GeminiIntentResult."""
        try:
            if not isinstance(data, dict):
                return GeminiIntentResult(
                    intent="UNCLEAR",
                    is_fallback=True,
                    error="Invalid payload: expected dict"
                )

            # Check if prompt was blocked by safety filters
            prompt_feedback = data.get("promptFeedback")
            if isinstance(prompt_feedback, dict):
                block_reason = prompt_feedback.get("blockReason")
                if block_reason:
                    return GeminiIntentResult(
                        intent="UNCLEAR",
                        is_fallback=True,
                        error=f"Prompt blocked: {block_reason}"
                    )

            candidates = data.get("candidates")
            if not isinstance(candidates, list) or not candidates:
                return GeminiIntentResult(
                    intent="UNCLEAR",
                    is_fallback=True,
                    error="No candidates returned by Gemini"
                )

            first_candidate = candidates[0]
            if not isinstance(first_candidate, dict):
                return GeminiIntentResult(
                    intent="UNCLEAR",
                    is_fallback=True,
                    error="Invalid candidate format in Gemini response"
                )

            finish_reason = first_candidate.get("finishReason")
            if finish_reason and finish_reason in {"SAFETY", "RECITATION", "BLOCKLIST"}:
                return GeminiIntentResult(
                    intent="UNCLEAR",
                    is_fallback=True,
                    error=f"Candidate blocked: finishReason={finish_reason}"
                )

            content = first_candidate.get("content")
            if not isinstance(content, dict):
                return GeminiIntentResult(
                    intent="UNCLEAR",
                    is_fallback=True,
                    error="Missing or invalid content in Gemini candidate"
                )

            parts = content.get("parts")
            if not isinstance(parts, list) or not parts or not isinstance(parts[0], dict):
                return GeminiIntentResult(
                    intent="UNCLEAR",
                    is_fallback=True,
                    error="Empty candidate parts in Gemini response"
                )

            raw_text = parts[0].get("text", "")
            cleaned_json = GeminiService.clean_json_text(raw_text)
            parsed = json.loads(cleaned_json)

            if not isinstance(parsed, dict):
                return GeminiIntentResult(
                    intent="UNCLEAR",
                    is_fallback=True,
                    error="Model output is not a JSON object"
                )

            raw_intent = str(parsed.get("intent", "")).strip().upper()
            validated_intent = raw_intent if raw_intent in SUPPORTED_INTENTS else "UNCLEAR"

            raw_confidence = parsed.get("confidence", 0.0)
            try:
                confidence = float(raw_confidence)
            except (ValueError, TypeError):
                confidence = 0.0

            target_lang = parsed.get("target_language")
            if target_lang and str(target_lang).strip().lower() in {"en", "mr"}:
                target_lang = str(target_lang).strip().lower()
            else:
                target_lang = None

            return GeminiIntentResult(
                intent=validated_intent,
                confidence=confidence,
                detected_language=parsed.get("detected_language"),
                target_language=target_lang,
                ticket_id=parsed.get("ticket_id"),
                contextual_reply=parsed.get("contextual_reply"),
                is_fallback=False
            )
        except json.JSONDecodeError as jde:
            logger.warning("[GEMINI] Failed to parse model JSON output: %s", str(jde))
            return GeminiIntentResult(
                intent="UNCLEAR",
                is_fallback=True,
                error="Invalid JSON from Gemini"
            )
        except Exception as exc:
            logger.error("[GEMINI] Unexpected error parsing Gemini response: %s", str(exc))
            return GeminiIntentResult(
                intent="UNCLEAR",
                is_fallback=True,
                error=f"Parsing error: {type(exc).__name__}"
            )

    @classmethod
    def classify_and_respond(
        cls,
        user_text: str,
        preferred_language: str = "mr"
    ) -> GeminiIntentResult:
        """
        Classifies user intent and generates contextual civic responses using Gemini API.
        Falls back gracefully if the API key is unconfigured, times out, or fails.
        """
        api_key = config.GEMINI_API_KEY
        if not api_key:
            logger.debug("[GEMINI] GEMINI_API_KEY is not configured; bypassing AI classification.")
            return GeminiIntentResult(
                intent=None,
                is_fallback=True,
                error="GEMINI_API_KEY_NOT_CONFIGURED"
            )

        clean_input = (user_text or "").strip()
        if not clean_input:
            return GeminiIntentResult(
                intent="UNCLEAR",
                confidence=1.0,
                is_fallback=False
            )

        model = config.GEMINI_MODEL or "gemini-2.5-flash"
        timeout_sec = float(getattr(config, "GEMINI_TIMEOUT_SECONDS", 4.0))

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}

        lang_instruction = (
            "Preferred citizen language: Marathi (मराठी)."
            if preferred_language == "mr"
            else "Preferred citizen language: English."
        )

        prompt_content = (
            f"{lang_instruction}\n\n"
            f"Citizen message:\n\"\"\"{clean_input[:1000]}\"\"\""
        )

        payload = {
            "system_instruction": {
                "parts": [
                    {"text": cls.SYSTEM_PROMPT}
                ]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": prompt_content}
                    ]
                }
            ],
            "generationConfig": {
                "response_mime_type": "application/json",
                "temperature": 0.1,
                "max_output_tokens": 512
            }
        }

        try:
            with httpx.Client(timeout=timeout_sec) as client:
                response = client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                return cls.parse_gemini_payload(data)

        except httpx.TimeoutException:
            logger.warning("[GEMINI] Classification request timed out after %.2f seconds.", timeout_sec)
            return GeminiIntentResult(
                intent=None,
                is_fallback=True,
                error="GEMINI_TIMEOUT"
            )
        except httpx.HTTPStatusError as http_err:
            safe_msg = cls._sanitize_error_message(str(http_err))
            logger.warning("[GEMINI] API returned HTTP error: %s", safe_msg)
            return GeminiIntentResult(
                intent=None,
                is_fallback=True,
                error=f"HTTP_{http_err.response.status_code}"
            )
        except httpx.RequestError as req_err:
            safe_msg = cls._sanitize_error_message(str(req_err))
            logger.warning("[GEMINI] Network/connection error contacting Gemini API: %s", safe_msg)
            return GeminiIntentResult(
                intent=None,
                is_fallback=True,
                error="GEMINI_NETWORK_ERROR"
            )
        except Exception as exc:
            safe_msg = cls._sanitize_error_message(str(exc))
            logger.warning("[GEMINI] Classification failed (%s): %s", type(exc).__name__, safe_msg)
            return GeminiIntentResult(
                intent=None,
                is_fallback=True,
                error=f"API_FAILURE_{type(exc).__name__}"
            )
