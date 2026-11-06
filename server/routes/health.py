from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
import logging
import time
from server.database.db import get_db

router = APIRouter(prefix="/api", tags=["Health & Public"])
logger = logging.getLogger(__name__)


@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    """
    Liveness and readiness probe.
    Returns HTTP 200 with db='ok' when the database is reachable,
    or HTTP 503 with db='error' when the database connection fails.
    Render uses this path to decide whether to route traffic to this instance.
    """
    ts = time.time()
    try:
        db.execute(text("SELECT 1"))
        return {
            "status": "healthy",
            "service": "EcoPulse AI Backend",
            "db": "ok",
            "timestamp": ts,
        }
    except Exception as exc:
        logger.error("[HEALTH] Database probe failed: %s", type(exc).__name__)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "degraded",
                "service": "EcoPulse AI Backend",
                "db": "error",
                "detail": "Database connection failed",
                "timestamp": ts,
            },
        )


@router.get("/notifications")
def get_public_notifications(db: Session = Depends(get_db)):
    from server.services.admin_service import AdminService
    return AdminService.get_public_broadcasts(db)
