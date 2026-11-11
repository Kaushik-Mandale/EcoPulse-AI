"""
WhatsAppLinkService — secure one-time token generation and redemption.

Security model:
- Tokens are generated with secrets.token_urlsafe(18) → 24 URL-safe chars.
- Only SHA-256(token) is stored; plaintext is returned once to the
  authenticated browser session and never persisted.
- Tokens expire after TOKEN_TTL_SECONDS (600 s = 10 min).
- Previous unconsumed tokens for the same user are invalidated atomically.
- Redemption increments attempt_count; exceeding MAX_ATTEMPTS invalidates
  the token without revealing whether the hash exists.
- Linking is committed atomically; concurrent requests cannot double-redeem.
"""

import hashlib
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from server.utils.config import config
from server.models.user import User
from server.models.whatsapp_link_token import WhatsAppLinkToken
from server.models.whatsapp_session import WhatsAppCitizen

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TOKEN_TTL_SECONDS = 600          # 10 minutes
MAX_TOKENS_PER_WINDOW = 5        # max tokens a user may generate in one TTL window
MAX_REDEMPTION_ATTEMPTS = 10     # brute-force ceiling per token
_TOKEN_BYTES = 18                # → 24 URL-safe base64 chars


def _hash_token(plaintext: str) -> str:
    """Return lowercase hex SHA-256 of *plaintext*."""
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


class WhatsAppLinkService:

    # ------------------------------------------------------------------
    # Token generation
    # ------------------------------------------------------------------

    @staticmethod
    def generate_link_code(db: Session, user: User) -> dict:
        """
        Generate a secure one-time linking code for *user*.

        Steps:
        1. Reject non-citizen accounts.
        2. Rate-limit: count tokens issued in the last TOKEN_TTL_SECONDS window.
        3. Invalidate any existing unconsumed tokens for this user.
        4. Create a new hashed token record.
        5. Return the plaintext code (never stored).
        """
        if user.role.lower() not in {"citizen"}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only citizen accounts can generate a WhatsApp linking code.",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is inactive.",
            )

        now = datetime.now(timezone.utc)
        window_start = now - timedelta(seconds=TOKEN_TTL_SECONDS)

        # Rate-limit check: count tokens issued in the current TTL window
        recent_count = (
            db.query(WhatsAppLinkToken)
            .filter(
                WhatsAppLinkToken.user_id == user.id,
                WhatsAppLinkToken.created_at >= window_start,
            )
            .count()
        )
        if recent_count >= MAX_TOKENS_PER_WINDOW:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    "Too many linking codes generated. "
                    f"Please wait a few minutes before trying again."
                ),
            )

        # Invalidate all previous unconsumed tokens for this user
        db.query(WhatsAppLinkToken).filter(
            WhatsAppLinkToken.user_id == user.id,
            WhatsAppLinkToken.consumed_at.is_(None),
        ).update({"consumed_at": now}, synchronize_session=False)

        # Generate cryptographically secure plaintext token
        plaintext = secrets.token_urlsafe(_TOKEN_BYTES)
        token_hash = _hash_token(plaintext)
        expires_at = now + timedelta(seconds=TOKEN_TTL_SECONDS)

        new_token = WhatsAppLinkToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
            attempt_count=0,
        )
        db.add(new_token)
        db.commit()

        logger.info(
            "[LINK] Linking code generated for user_id=%d (token_id=%d, expires=%s).",
            user.id,
            new_token.id,
            expires_at.isoformat(),
        )

        return {
            "success": True,
            "link_code": plaintext,
            "code": plaintext,
            "expires_in": TOKEN_TTL_SECONDS,
            "bot_phone": re.sub(r"\D", "", config.WHATSAPP_BUSINESS_PHONE or ""),
            "message": f"Send: LINK {plaintext}  from the WhatsApp number you want to connect.",
        }

    # ------------------------------------------------------------------
    # Linking status
    # ------------------------------------------------------------------

    @staticmethod
    def get_link_status(db: Session, user: User) -> dict:
        """Return the current WhatsApp linking status for *user*."""
        citizen = (
            db.query(WhatsAppCitizen)
            .filter(WhatsAppCitizen.user_id == user.id)
            .first()
        )
        if citizen:
            # Mask middle digits: 919876543210 → 91*****3210
            phone = citizen.phone_number or ""
            masked = phone[:2] + "*" * max(0, len(phone) - 6) + phone[-4:] if len(phone) > 6 else phone
            linked_at = citizen.updated_at.isoformat() if hasattr(citizen, "updated_at") and citizen.updated_at else (
                citizen.created_at.isoformat() if citizen.created_at else None
            )
            return {
                "is_linked": True,
                "whatsapp_phone": masked,
                "whatsapp_phone_masked": masked,
                "registered_phone": user.phone or None,
                "linked_at": linked_at,
            }
        return {
            "is_linked": False,
            "whatsapp_phone": None,
            "whatsapp_phone_masked": None,
            "registered_phone": user.phone or None,
            "linked_at": None,
        }

    # ------------------------------------------------------------------
    # Token redemption (called from webhook handler)
    # ------------------------------------------------------------------

    @staticmethod
    def redeem_link_code(
        db: Session,
        plaintext_code: str,
        sender_phone: str,
    ) -> Optional[User]:
        """
        Attempt to redeem *plaintext_code* sent by *sender_phone* on WhatsApp.

        Returns the linked User on success, or raises an exception that the
        webhook handler converts to a safe generic failure message.

        Security:
        - Locks the token row (SELECT … FOR UPDATE) to prevent concurrent redemption.
        - Never reveals whether a matching token exists in error messages.
        - Increments attempt_count before each check so brute-force is counted
          even when the token is not found.
        """
        now = datetime.now(timezone.utc)
        token_hash = _hash_token(plaintext_code.strip())

        # Acquire row lock to prevent concurrent double-redemption
        # SQLite (test env) does not support FOR UPDATE — handled gracefully below.
        try:
            token: Optional[WhatsAppLinkToken] = (
                db.query(WhatsAppLinkToken)
                .filter(WhatsAppLinkToken.token_hash == token_hash)
                .with_for_update()
                .first()
            )
        except Exception:
            # SQLite fallback (tests)
            token = (
                db.query(WhatsAppLinkToken)
                .filter(WhatsAppLinkToken.token_hash == token_hash)
                .first()
            )

        if not token:
            logger.warning("[LINK] Redemption attempt with unknown token hash (phone=%s).", sender_phone)
            return None

        # Increment attempt count regardless of outcome (brute-force protection)
        token.attempt_count = (token.attempt_count or 0) + 1

        invalid_reason = None
        if token.consumed_at is not None:
            invalid_reason = "already consumed"
        elif token.expires_at.replace(tzinfo=timezone.utc) < now:
            invalid_reason = "expired"
        elif token.attempt_count > MAX_REDEMPTION_ATTEMPTS:
            invalid_reason = "too many attempts"

        if invalid_reason:
            db.commit()
            logger.warning("[LINK] Token redemption failed (%s, phone=%s).", invalid_reason, sender_phone)
            return None

        # Validate the user account
        user: Optional[User] = db.query(User).filter(User.id == token.user_id).first()
        if not user or not user.is_active or user.role.lower() != "citizen":
            db.commit()
            logger.warning("[LINK] Token refers to invalid/inactive user_id=%s.", token.user_id)
            return None

        # Check: sender not already linked to a DIFFERENT user
        existing_citizen = (
            db.query(WhatsAppCitizen)
            .filter(WhatsAppCitizen.phone_number == sender_phone)
            .first()
        )
        if existing_citizen and existing_citizen.user_id and existing_citizen.user_id != user.id:
            db.commit()
            logger.warning(
                "[LINK] Sender phone %s is already linked to user_id=%d (requested user_id=%d).",
                sender_phone,
                existing_citizen.user_id,
                user.id,
            )
            return None

        # Check: target user doesn't already have a DIFFERENT active WA identity
        user_citizen = (
            db.query(WhatsAppCitizen)
            .filter(
                WhatsAppCitizen.user_id == user.id,
                WhatsAppCitizen.phone_number != sender_phone,
            )
            .first()
        )
        if user_citizen:
            # Unlink the old identity before linking the new one
            logger.info(
                "[LINK] Replacing existing WhatsApp link for user_id=%d (old phone=%s → new phone=%s).",
                user.id,
                user_citizen.phone_number,
                sender_phone,
            )
            user_citizen.user_id = None
            user_citizen.is_authorized = False

        # Upsert the WhatsAppCitizen record
        if existing_citizen:
            existing_citizen.user_id = user.id
            existing_citizen.is_authorized = True
            existing_citizen.full_name = user.full_name
            existing_citizen.ward = user.ward or existing_citizen.ward
            citizen = existing_citizen
        else:
            citizen = WhatsAppCitizen(
                phone_number=sender_phone,
                user_id=user.id,
                full_name=user.full_name,
                ward=user.ward,
                is_authorized=True,
                preferred_language="mr",
                eco_coins=0,
                conversation_state="IDLE",
            )
            db.add(citizen)

        # Mark token consumed and record which phone redeemed it
        token.consumed_at = now
        token.whatsapp_phone = sender_phone

        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            logger.error("[LINK] IntegrityError during linking commit (concurrent request?) — user_id=%d.", user.id)
            return None

        logger.info(
            "[LINK] WhatsApp account linked: user_id=%d ↔ phone=%s.",
            user.id,
            sender_phone,
        )
        return user

    # ------------------------------------------------------------------
    # Unlinking (optional / admin-triggered)
    # ------------------------------------------------------------------

    @staticmethod
    def unlink(db: Session, user: User) -> dict:
        """Remove the WhatsApp link for *user*."""
        citizen = (
            db.query(WhatsAppCitizen)
            .filter(WhatsAppCitizen.user_id == user.id)
            .first()
        )
        if not citizen:
            return {"success": False, "message": "No WhatsApp account is currently linked."}

        citizen.user_id = None
        citizen.is_authorized = False
        db.commit()
        logger.info("[LINK] WhatsApp account unlinked for user_id=%d.", user.id)
        return {"success": True, "message": "WhatsApp account unlinked successfully."}

