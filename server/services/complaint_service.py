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
        if user_id:
            complaints = db.query(Complaint).filter(Complaint.citizen_id == user_id).order_by(Complaint.id.desc()).all()
            if complaints:
                return [ComplaintService._to_response(c) for c in complaints]
        return ComplaintService.get_all_complaints(db)

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

        return ComplaintService._to_response(new_complaint)

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
    def _to_response(c: Complaint) -> ComplaintResponse:
        status_color = "bg-emerald-100 text-emerald-800 border-emerald-300"
        if c.status == "Pending":
            status_color = "bg-red-100 text-red-800 border-red-300"
        elif c.status == "In Progress":
            status_color = "bg-yellow-100 text-yellow-800 border-yellow-300"

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
            image_url=c.image_url,
            ai_status=c.ai_status or "Verified",
            ai_confidence=c.ai_confidence or 0.95
        )
