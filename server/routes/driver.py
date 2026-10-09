from fastapi import APIRouter, Depends, HTTPException, status
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
        return DriverService.update_task_status(db, task_id, payload.status, payload.proof_image_url, current_user)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

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
