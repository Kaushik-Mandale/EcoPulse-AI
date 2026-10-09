from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
import time
from server.database.db import get_db

router = APIRouter(prefix="/api", tags=["Health & Public"])

@router.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "CITY_SWAP Backend",
        "timestamp": time.time()
    }

@router.get("/notifications")
def get_public_notifications(db: Session = Depends(get_db)):
    from server.services.admin_service import AdminService
    return AdminService.get_public_broadcasts(db)
