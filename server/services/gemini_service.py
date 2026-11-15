import json
import logging
import re
from typing import Optional, Literal
from pydantic import BaseModel, Field
import httpx

from server.utils.config import config

logger = logging.getLogger(__name__)

# Allowed initial intent categories as specified by Phase 1 requirements
SUPPORTED_INTENTS = {
    "REPORT_WASTE",
    "GENERAL_COMPLAINT",
    "TRACK_COMPLAINT",
    "MUNICIPAL_FAQ",
    "CHANGE_LANGUAGE",
    "GREETING",
    "OPEN_MENU",
    "UNCLEAR",
}


class GeminiIntentResult(BaseModel):
    """Structured representation of Gemini intent classification and response."""
    intent: Optional[Literal[
        "REPORT_WASTE",
        "GENERAL_COMPLAINT",
        "TRACK_COMPLAINT",
        "MUNICIPAL_FAQ",
        "CHANGE_LANGUAGE",
        "GREETING",
        "OPEN_MENU",
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
        "   - \"REPORT_WASTE\": citizen wants to report garbage, trash, overflow, debris, dead animal, or uncollected waste.\n"
        "   - \"GENERAL_COMPLAINT\": citizen wants to report non-waste municipal issues (streetlights, drainage, potholes, staff, water leakage).\n"
        "   - \"TRACK_COMPLAINT\": citizen wants to check complaint status or view past complaints.\n"
        "   - \"MUNICIPAL_FAQ\": citizen asks a question about municipal timings, EcoCoins, property tax rebates, waste segregation, helpline, or civic procedures.\n"
        "   - \"CHANGE_LANGUAGE\": citizen asks to switch or change language (e.g. 'speak in English', 'मराठीत बोला').\n"
        "   - \"GREETING\": citizen says hi, hello, namaskar, good morning, start, etc.\n"
        "   - \"OPEN_MENU\": citizen asks to see the menu, services list, or all options.\n"
        "   - \"UNCLEAR\": message is ambiguous, random, or not understood.\n\n"
        "2. \"confidence\": float between 0.0 and 1.0.\n"
        "3. \"detected_language\": \"mr\", \"en\", or \"mixed\".\n"
        "4. \"target_language\": \"mr\" or \"en\" if intent is CHANGE_LANGUAGE, else null.\n"
        "5. \"ticket_id\": complaint tracking number if present (e.g. DHL-2026-W12-XYZ), else null.\n"
        "6. \"contextual_reply\": \n"
        "   - For MUNICIPAL_FAQ: provide a concise, factual 1-3 sentence civic answer in the citizen's preferred language.\n"
        "   - For UNCLEAR: provide a polite 1-2 sentence clarification in the citizen's preferred language.\n"
        "   - For other intents: null.\n\n"
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
        # Redact query string key parameter if present
        return re.sub(r'([?&]key=)[^&\s]+', r'\1[REDACTED]', str(err_str))

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
            candidates = data.get("candidates", [])
            if not candidates:
                return GeminiIntentResult(
                    intent="UNCLEAR",
                    is_fallback=True,
                    error="No candidates returned by Gemini"
                )

            parts = candidates[0].get("content", {}).get("parts", [])
            if not parts:
                return GeminiIntentResult(
                    intent="UNCLEAR",
                    is_fallback=True,
                    error="Empty candidate parts in Gemini response"
                )

            raw_text = parts[0].get("text", "")
            cleaned_json = GeminiService.clean_json_text(raw_text)
            parsed = json.loads(cleaned_json)

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
        except Exception as exc:
            safe_msg = cls._sanitize_error_message(str(exc))
            logger.warning("[GEMINI] Classification failed (%s): %s", type(exc).__name__, safe_msg)
            return GeminiIntentResult(
                intent=None,
                is_fallback=True,
                error=f"API_FAILURE_{type(exc).__name__}"
            )
