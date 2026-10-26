import hmac
import hashlib
from fastapi import HTTPException, status
from server.services.media_storage import get_media_storage
from server.utils.security import get_jwt_secret
from server.utils.config import config
import secrets
import string
import logging
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List, Optional
from server.models.complaint import Complaint
from server.models.task import DriverTask
from server.models.user import User
from server.schemas.complaint import ComplaintCreate, ComplaintResponse
from server.services.ai_service import AIService

logger = logging.getLogger(__name__)

# Uppercase alphanumeric alphabet, ambiguous characters (I, O) excluded to
# reduce transcription errors.  9 characters → ~47 bits of entropy, keeping
# the total tracking number well inside the String(30) column limit.
_ID_ALPHABET = (string.ascii_uppercase + string.digits).translate(
    str.maketrans("", "", "IO")
)
_ID_SUFFIX_LEN = 9
_MAX_RETRIES = 5


def _generate_web_tracking_id() -> str:
    """Generate a collision-resistant web complaint tracking number.

    Format: EP-2026-<9 uppercase alphanumeric chars>
    Example: EP-2026-A7BZ3XKQR
    Total length: 18 chars — fits String(30).
    """
    suffix = "".join(secrets.choice(_ID_ALPHABET) for _ in range(_ID_SUFFIX_LEN))
    return f"EP-2026-{suffix}"


def _is_tracking_number_collision(exc: Exception) -> bool:
    """Return True only when *exc* is a duplicate-key error specifically for
    the complaints.tracking_number column.

    Checks two layers:
    1. The exception must be a SQLAlchemy IntegrityError (or wrap one as
       its ``__cause__`` / ``__context__``), meaning the database itself
       raised a constraint violation — not just any exception whose string
       happens to contain the word "integrity".
    2. The underlying database error message must reference the
       ``tracking_number`` column (SQLite: "complaints.tracking_number";
       PostgreSQL: "complaints_tracking_number_key" or the column name).

    This prevents suppressing unrelated integrity errors such as NOT NULL
    violations on other columns, foreign-key violations, or check-constraint
    failures.
    """
    # Walk the exception chain to find the IntegrityError
    candidate = exc
    found_integrity = False
    for _ in range(5):  # avoid infinite loops on circular chains
        if isinstance(candidate, IntegrityError):
            found_integrity = True
            break
        if candidate.__cause__ is not None:
            candidate = candidate.__cause__
        elif candidate.__context__ is not None:
            candidate = candidate.__context__
        else:
            break

    if not found_integrity:
        return False

    # Confirm the violation is for tracking_number specifically by inspecting
    # the original database driver error string.  Both SQLite and PostgreSQL
    # include the column name in their error messages.
    orig = getattr(candidate, "orig", None)
    orig_str = str(orig).lower() if orig is not None else ""
    params_str = str(getattr(candidate, "params", "")).lower()
    statement_str = str(getattr(candidate, "statement", "")).lower()

    # SQLite:    "UNIQUE constraint failed: complaints.tracking_number"
    # PostgreSQL:"duplicate key value violates unique constraint
    #             \"complaints_tracking_number_key\""
    # Also check the params/statement in case orig is opaque.
    haystack = " ".join([orig_str, params_str, statement_str])
    return "tracking_number" in haystack


class ComplaintService:
    @staticmethod
    def get_all_complaints(db: Session) -> List[ComplaintResponse]:
        complaints = db.query(Complaint).order_by(Complaint.id.desc()).all()
        if not complaints:
            # Seed default complaints matching CITIZEN.png & ADMIN DASHBOARD.png
            ComplaintService.seed_default_complaints(db)
            complaints = db.query(Complaint).order_by(Complaint.id.desc()).all()

        return [ComplaintService._to_response(c) for c in complaints]

    @staticmethod
    def get_user_complaints(db: Session, user_id: Optional[int]) -> List[ComplaintResponse]:
        """Returns complaints submitted by a specific user.
        If user_id is None or the user has no complaints, returns an empty list
        to prevent leaking other citizens' complaints.
        """
        if not user_id:
            return []
        complaints = db.query(Complaint).filter(Complaint.citizen_id == user_id).order_by(Complaint.id.desc()).all()
        return [ComplaintService._to_response(c) for c in complaints]

    @staticmethod
    def get_complaint_by_tracking_or_id(db: Session, identifier: str) -> Optional[ComplaintResponse]:
        clean_id = identifier.strip()
        # Try finding by tracking number (legacy EP-2026-NNNNN and new EP-2026-XXXXXXXXX both matched)
        complaint = db.query(Complaint).filter(Complaint.tracking_number.ilike(clean_id)).first()
        if not complaint and clean_id.isdigit():
            complaint = db.query(Complaint).filter(Complaint.id == int(clean_id)).first()
        if complaint:
            return ComplaintService._to_response(complaint)
        return None

    @staticmethod
    def generate_tracking_token(complaint_id: int, tracking_number: str) -> str:
        """Generates a high-entropy HMAC-SHA256 tracking token for complaint images.
        Derived from server SECRET_KEY — cannot be forged by guessing tracking IDs.
        """
        secret = get_jwt_secret().encode("utf-8")
        msg = f"ecopulse:tracking:{complaint_id}:{tracking_number}".encode("utf-8")
        return hmac.new(secret, msg, hashlib.sha256).hexdigest()

    @staticmethod
    def verify_tracking_token(complaint_id: int, tracking_number: str, token: Optional[str]) -> bool:
        """Verifies a tracking token in constant time."""
        if not token or not token.strip():
            return False
        expected = ComplaintService.generate_tracking_token(complaint_id, tracking_number)
        return hmac.compare_digest(token.strip(), expected)

    @staticmethod
    def authorize_and_resolve_image(
        db: Session,
        complaint_id: str,
        current_user: Optional[User] = None,
        tracking_token: Optional[str] = None,
    ) -> dict:
        """Enforces backend-mediated authorization before generating a signed image URL.

        Authorization rules:
        - Admin / Collector: full access to all complaint images.
        - Assigned Driver: access to images for complaints linked to their tasks.
        - Citizen: access strictly to their own submitted complaint images.
        - Anonymous Citizen Tracking: requires high-entropy tracking token.
        - Arbitrary client storage keys are NEVER trusted as proof of access.
        """
        clean_id = (complaint_id or "").strip()
        complaint = db.query(Complaint).filter(Complaint.tracking_number.ilike(clean_id)).first()
        if not complaint and clean_id.isdigit():
            complaint = db.query(Complaint).filter(Complaint.id == int(clean_id)).first()

        if not complaint:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Complaint with reference '{clean_id}' not found."
            )

        if not complaint.image_url:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Complaint does not have an associated image."
            )

        # 1. Admin or Collector: full administrative visibility
        if current_user and current_user.role.lower() in ("admin", "collector"):
            return ComplaintService._format_resolved_image(complaint)

        # 2. Driver: authorized only if assigned to this complaint
        if current_user and current_user.role.lower() == "driver":
            is_assigned = (
                complaint.assigned_driver_id == current_user.id
                or db.query(DriverTask).filter(
                    DriverTask.complaint_id == complaint.id,
                    DriverTask.driver_id == current_user.id
                ).first() is not None
            )
            if not is_assigned:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access forbidden: Driver is not assigned to this complaint."
                )
            return ComplaintService._format_resolved_image(complaint)

        # 3. Citizen: authorized only for their own complaints
        if current_user and current_user.role.lower() == "citizen":
            if complaint.citizen_id is not None and complaint.citizen_id == current_user.id:
                return ComplaintService._format_resolved_image(complaint)
            if complaint.citizen_id is not None and complaint.citizen_id != current_user.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access forbidden: You do not have permission to view this complaint image."
                )
            # If complaint was submitted anonymously (citizen_id is None), check tracking token

        # 4. Anonymous tracking: requires high-entropy tracking token
        token = (tracking_token or "").strip()
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication or valid tracking token required to access private complaint image.",
                headers={"WWW-Authenticate": "Bearer"}
            )

        is_valid = ComplaintService.verify_tracking_token(complaint.id, complaint.tracking_number, token)
        # Check optional stored tracking_secret if column exists
        if not is_valid and getattr(complaint, "tracking_secret", None):
            is_valid = hmac.compare_digest(token, getattr(complaint, "tracking_secret"))

        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access forbidden: Invalid tracking token for this complaint image."
            )

        return ComplaintService._format_resolved_image(complaint)

    @staticmethod
    def _format_resolved_image(complaint: Complaint) -> dict:
        raw_ref = complaint.image_url
        storage = get_media_storage()
        resolved_url = storage.get_url(raw_ref)
        is_supabase = raw_ref.startswith("supabase:")
        is_local = raw_ref.startswith("/uploads")
        ttl = getattr(config, "SUPABASE_SIGNED_URL_TTL_SECONDS", 900) if is_supabase else None
        return {
            "url": resolved_url,
            "complaint_id": complaint.tracking_number,
            "storage_type": "supabase" if is_supabase else ("local" if is_local else "external"),
            "expires_in": ttl
        }

    @staticmethod
    def create_complaint(db: Session, payload: ComplaintCreate, user: Optional[User] = None) -> ComplaintResponse:
        ai_res = AIService.verify_waste_image(payload.image_url, payload.type)

        new_complaint = None
        for attempt in range(_MAX_RETRIES):
            tracking_num = _generate_web_tracking_id()
            try:
                new_complaint = Complaint(
                    tracking_number=tracking_num,
                    citizen_id=user.id if user else None,
                    ward=payload.ward or "Ward 12",
                    location_address=payload.location,
                    latitude=payload.latitude,
                    longitude=payload.longitude,
                    waste_type=payload.type,
                    description=payload.description,
                    image_url=payload.image_url,
                    ai_status=ai_res["status"],
                    ai_confidence=ai_res["confidence"],
                    status="In Progress",
                    assigned_driver_name="Ramesh Y."
                )
                db.add(new_complaint)
                db.flush()
                # flush succeeded — tracking number is unique; exit retry loop
                break
            except Exception as exc:
                db.rollback()
                if _is_tracking_number_collision(exc):
                    if attempt < _MAX_RETRIES - 1:
                        logger.warning(
                            "[COMPLAINT] Tracking number collision on attempt %d/%d (%s); retrying.",
                            attempt + 1,
                            _MAX_RETRIES,
                            tracking_num,
                        )
                        continue
                    # All retries exhausted
                    raise RuntimeError(
                        f"Could not generate a unique web tracking number after {_MAX_RETRIES} attempts."
                    ) from exc
                # Not a tracking-number collision — re-raise without concealing
                raise

        db.commit()
        db.refresh(new_complaint)

        # Automatically create driver task for collection
        new_task = DriverTask(
            complaint_id=new_complaint.id,
            location_name=f"{new_complaint.location_address}",
            status="Pending"
        )
        db.add(new_task)
        db.commit()

        # Reward citizen with EcoCoins
        if user:
            user.eco_coins = (user.eco_coins or 100) + 25
            db.commit()

        is_anonymous = user is None
        return ComplaintService._to_response(new_complaint, include_tracking_token=is_anonymous)

    @staticmethod
    def assign_driver(db: Session, complaint_id: int, driver_name: str) -> ComplaintResponse:
        complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
        if complaint:
            complaint.assigned_driver_name = driver_name
            complaint.status = "In Progress"
            db.commit()
            db.refresh(complaint)
            return ComplaintService._to_response(complaint)
        raise Exception(f"Complaint {complaint_id} not found")

    @staticmethod
    def seed_default_complaints(db: Session):
        seeds = [
            Complaint(
                tracking_number="EP-2026-00123",
                ward="Ward 12",
                location_address="Green Park, Ward 12",
                waste_type="Mixed Waste",
                status="In Progress",
                assigned_driver_name="Ramesh Y.",
                ai_status="Verified",
                ai_confidence=0.98
            ),
            Complaint(
                tracking_number="EP-2026-00122",
                ward="Ward 8",
                location_address="Sai Nagar, Ward 8",
                waste_type="Garbage Overflow",
                status="Pending",
                assigned_driver_name="Suresh K.",
                ai_status="Verified",
                ai_confidence=0.94
            ),
            Complaint(
                tracking_number="EP-2026-00121",
                ward="Ward 4",
                location_address="Market Area, Ward 4",
                waste_type="Plastic Waste",
                status="Completed",
                assigned_driver_name="Ajay P.",
                ai_status="Verified",
                ai_confidence=0.99
            )
        ]
        db.add_all(seeds)
        db.commit()

    @staticmethod
    def _resolve_image_url(raw_url: Optional[str], tracking_number: Optional[str] = None) -> Optional[str]:
        """Resolves an image reference safely for public complaint responses.

        - 'supabase:...' references: Never leak signed Supabase URLs into public list responses.
          Instead, returns a mediated endpoint URL pointing to the authorized backend endpoint.
        - '/uploads/...' local paths: returned unchanged.
        - 'http(s)://...' or 'data:...' URLs: returned unchanged.
        - None: None
        """
        if not raw_url:
            return raw_url
        if raw_url.startswith("supabase:") or raw_url.startswith("r2:"):
            if tracking_number:
                return f"/api/complaints/{tracking_number}/image"
            return None
        return raw_url

    @staticmethod
    def _to_response(c: Complaint, include_tracking_token: bool = False) -> ComplaintResponse:
        status_color = "bg-emerald-100 text-emerald-800 border-emerald-300"
        if c.status == "Pending":
            status_color = "bg-red-100 text-red-800 border-red-300"
        elif c.status == "In Progress":
            status_color = "bg-yellow-100 text-yellow-800 border-yellow-300"

        tracking_token = None
        if include_tracking_token:
            tracking_token = ComplaintService.generate_tracking_token(c.id, c.tracking_number)

        return ComplaintResponse(
            id=c.tracking_number,
            db_id=c.id,
            location=c.location_address,
            type=c.waste_type,
            ward=c.ward,
            status=c.status,
            assignedTo=c.assigned_driver_name or "Unassigned",
            time="10 mins ago" if c.status == "In Progress" else ("25 mins ago" if c.status == "Pending" else "1 hour ago"),
            statusColor=status_color,
            image_url=ComplaintService._resolve_image_url(c.image_url, c.tracking_number),
            ai_status=c.ai_status or "Verified",
            ai_confidence=c.ai_confidence or 0.95,
            tracking_token=tracking_token,
        )
