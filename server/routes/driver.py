from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List
from server.database.db import get_db
from server.schemas.task import DriverTaskResponse, DriverTaskStatusUpdate
from server.schemas.driver import (
    PerformanceOverviewResponse, FuelLogsSummaryResponse, FuelLogResponse,
    FuelLogCreate, MessagesOverviewResponse, MessageResponse, MessageCreate
)
from server.services.driver_service import DriverService
from server.utils.security import get_current_driver_user
from server.models.user import User
from server.services.task_lifecycle_service import transition_driver_task, add_evidence, submit_for_verification
from server.services.whatsapp_service import validate_image_content, MediaValidationError
from server.services.media_storage import get_media_storage
from server.utils.config import config
import os
import uuid

router = APIRouter(prefix="/api/driver", tags=["Driver Portal"])

@router.get("/tasks", response_model=List[DriverTaskResponse])
def get_driver_tasks(db: Session = Depends(get_db), current_user: User = Depends(get_current_driver_user)):
    return DriverService.get_driver_tasks(db, current_user)

@router.patch("/tasks/{task_id}/status", response_model=DriverTaskResponse)
def update_task_status(
    task_id: int,
    payload: DriverTaskStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_driver_user)
):
    try:
        if payload.status == "Completed":
            # Delegate to the ownership-aware service before returning the
            # completion prohibition so this endpoint never bypasses scope checks.
            return DriverService.update_task_status(db, task_id, payload.status, payload.proof_image_url, current_user)
        if payload.status == "In Progress":
            task = transition_driver_task(db, task_id, current_user, "start")
            return DriverService._to_response(task, db)
        raise HTTPException(409, "Use the task accept/start workflow; direct status changes are not allowed.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/tasks/{task_id}/accept", response_model=DriverTaskResponse)
def accept_driver_task(task_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_driver_user)):
    task = transition_driver_task(db, task_id, current_user, "accept")
    return DriverService._to_response(task, db)


@router.post("/tasks/{task_id}/start", response_model=DriverTaskResponse)
def start_driver_task(task_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_driver_user)):
    task = transition_driver_task(db, task_id, current_user, "start")
    return DriverService._to_response(task, db)


async def _validated_image(file: UploadFile | None):
    if file is None:
        return None
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext and ext not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise HTTPException(400, "Unsupported evidence image extension.")
    content = await file.read(config.MAX_UPLOAD_SIZE + 1)
    await file.close()
    if not content:
        raise HTTPException(400, "Evidence image is empty.")
    if len(content) > config.MAX_UPLOAD_SIZE:
        raise HTTPException(413, "Evidence image exceeds the configured upload limit.")
    try:
        mime, detected_ext = validate_image_content(content, file.content_type, config.MAX_UPLOAD_SIZE)
    except MediaValidationError as exc:
        raise HTTPException(400, str(exc)) from exc
    if ext and (".jpg" if ext == ".jpeg" else ext) != (".jpg" if detected_ext == ".jpeg" else detected_ext):
        raise HTTPException(400, "Evidence image extension does not match its content.")
    return content, mime, detected_ext


@router.post("/tasks/{task_id}/evidence")
async def upload_task_evidence(
    task_id: int,
    after_photo: UploadFile = File(...),
    before_photo: UploadFile | None = File(None),
    notes: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_driver_user),
):
    from server.models.task import DriverTask
    if not db.query(DriverTask).filter(DriverTask.id == task_id, DriverTask.driver_id == current_user.id).first():
        raise HTTPException(404, "Task not found.")
    after = await _validated_image(after_photo)
    before = await _validated_image(before_photo)
    storage = get_media_storage()
    try:
        after_ref = storage.save_image(after[0], after[2], after[1], f"task-{task_id}-{uuid.uuid4().hex}")
        before_ref = storage.save_image(before[0], before[2], before[1], f"task-{task_id}-{uuid.uuid4().hex}") if before else None
        evidence = add_evidence(db, task_id, current_user, before_ref, after_ref, notes)
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(500, "Evidence could not be stored.") from exc
    return {"id": evidence.id, "status": evidence.status, "collected_at": evidence.collected_at,
            "message": "Evidence saved. Submit it for verification when ready."}


@router.post("/tasks/{task_id}/submit-for-verification", response_model=DriverTaskResponse)
def request_task_verification(task_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_driver_user)):
    task = submit_for_verification(db, task_id, current_user)
    return DriverService._to_response(task, db)

@router.get("/performance", response_model=PerformanceOverviewResponse)
def get_driver_performance(db: Session = Depends(get_db), current_user: User = Depends(get_current_driver_user)):
    return DriverService.get_performance_data(db, current_user)

@router.get("/fuel-logs", response_model=FuelLogsSummaryResponse)
def get_driver_fuel_logs(db: Session = Depends(get_db), current_user: User = Depends(get_current_driver_user)):
    return DriverService.get_fuel_logs(db, current_user)

@router.post("/fuel-logs", response_model=FuelLogResponse, status_code=status.HTTP_201_CREATED)
def create_driver_fuel_log(
    payload: FuelLogCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_driver_user)
):
    try:
        return DriverService.create_fuel_log(db, current_user, payload.odometer, payload.liters, payload.cost)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.get("/messages", response_model=MessagesOverviewResponse)
def get_driver_messages(db: Session = Depends(get_db), current_user: User = Depends(get_current_driver_user)):
    return DriverService.get_messages(db, current_user)

@router.post("/messages", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
def send_driver_message(
    payload: MessageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_driver_user)
):
    try:
        return DriverService.send_message(db, current_user, payload.body)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
