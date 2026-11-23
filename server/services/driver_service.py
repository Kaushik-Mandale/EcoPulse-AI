from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from server.models.task import DriverTask
from server.models.complaint import Complaint
from server.models.user import User
from server.models.fuel_log import FuelLog
from server.models.performance import DriverPerformance
from server.models.message import Message
from server.models.task_evidence import TaskEvidence
from server.schemas.task import DriverTaskResponse
from server.schemas.driver import (
    PerformanceOverviewResponse, WeeklyTrendBar, Achievement, LeaderboardEntry,
    FuelLogsSummaryResponse, FuelLogResponse, MessagesOverviewResponse, MessageResponse,
    ConversationThread
)

VALID_TASK_STATUSES = {"Pending", "In Progress", "Completed"}

class DriverService:
    @staticmethod
    def get_driver_tasks(db: Session, driver: Optional[User] = None) -> List[DriverTaskResponse]:
        query = db.query(DriverTask)
        if driver:
            if driver.role != "driver":
                return []
            query = query.filter(DriverTask.driver_id == driver.id)

        tasks = query.order_by(DriverTask.id.asc()).all()
        return [DriverService._to_response(t, db) for t in tasks]

    @staticmethod
    def update_task_status(db: Session, task_id: int, new_status: str, proof_image: str = None, driver: Optional[User] = None) -> DriverTaskResponse:
        task = db.query(DriverTask).filter(DriverTask.id == task_id).first()
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Task {task_id} not found"
            )

        if new_status not in VALID_TASK_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid task status '{new_status}'. Allowed statuses: {', '.join(sorted(VALID_TASK_STATUSES))}"
            )

        # Enforce task ownership: only the assigned driver or an admin can update the task
        if driver and (driver.role != "driver" or task.driver_id != driver.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access forbidden: You can only modify tasks assigned to you."
            )

        if new_status == "Completed":
            raise HTTPException(status_code=409, detail="Completion requires Municipal Admin evidence verification.")
        if new_status != "In Progress" or task.status != "Accepted":
            raise HTTPException(status_code=409, detail="Use the authorized task lifecycle transitions.")

        task.status = new_status
        # Sync linked complaint status in PostgreSQL
        if task.complaint_id:
            complaint = db.query(Complaint).filter(Complaint.id == task.complaint_id).first()
            if complaint:
                if complaint.status != "Completed":
                    complaint.status = "In Progress"

        db.commit()
        db.refresh(task)
        return DriverService._to_response(task, db)

    @staticmethod
    def get_performance_data(db: Session, driver: User) -> PerformanceOverviewResponse:
        perf_records = db.query(DriverPerformance).filter(DriverPerformance.driver_id == driver.id).all()
        weekly_trends = [
            WeeklyTrendBar(
                day=record.date,
                h=f"{max(0, min(100, int(record.efficiency)))}%",
                active=False,
            )
            for record in sorted(perf_records, key=lambda item: item.date)
        ]
        avg_safety = int(sum(r.safety_score for r in perf_records) / len(perf_records)) if perf_records else None
        avg_fuel = round(sum(r.fuel_economy for r in perf_records) / len(perf_records), 1) if perf_records else None
        avg_efficiency = int(sum(r.efficiency for r in perf_records) / len(perf_records)) if perf_records else None

        return PerformanceOverviewResponse(
            collection_efficiency=f"{avg_efficiency}%" if avg_efficiency is not None else None,
            collection_efficiency_pct=None,
            eco_coins_balance=driver.eco_coins or 0,
            eco_coins_earned=None,
            fuel_economy=f"{avg_fuel} km/l" if avg_fuel is not None else None,
            fuel_economy_pct=None,
            safety_score=f"{avg_safety}/100" if avg_safety is not None else None,
            safety_score_pct=None,
            weekly_trends=weekly_trends,
            achievements=[],
            leaderboard=[]
        )

    @staticmethod
    def get_fuel_logs(db: Session, driver: User) -> FuelLogsSummaryResponse:
        logs = db.query(FuelLog).filter(FuelLog.driver_id == driver.id).order_by(FuelLog.created_at.desc()).all()
        total_spent = sum(log.cost for log in logs)

        return FuelLogsSummaryResponse(
            logs=[FuelLogResponse.model_validate(log) for log in logs],
            current_fuel_level=None,
            avg_consumption=None,
            total_spent=total_spent
        )

    @staticmethod
    def create_fuel_log(db: Session, driver: User, odometer: int, liters: float, cost: float) -> FuelLogResponse:
        # Create a new FuelLog row
        new_log = FuelLog(
            driver_id=driver.id,
            odometer=odometer,
            liters=liters,
            cost=cost
        )
        db.add(new_log)
        db.commit()
        db.refresh(new_log)
        return FuelLogResponse.model_validate(new_log)

    @staticmethod
    def get_messages(db: Session, driver: User) -> MessagesOverviewResponse:
        # Get messages involving this driver (either as recipient, or sent by them)
        messages = db.query(Message).filter(
            (Message.recipient_id == driver.id) | (Message.sender_id == driver.id)
        ).order_by(Message.created_at.asc()).all()

        threads_by_participant = {}
        for message in messages:
            if message.sender_id == driver.id:
                if message.recipient_id is None:
                    name, role = "Dispatch Center", "Dispatcher"
                else:
                    recipient = db.query(User).filter(User.id == message.recipient_id).first()
                    name = recipient.full_name if recipient else "Unknown recipient"
                    role = recipient.role if recipient else "Unknown"
            else:
                name, role = message.sender_name, message.sender_role

            key = (name, role)
            thread = threads_by_participant.get(key)
            if thread is None or message.created_at > thread["created_at"]:
                threads_by_participant[key] = {
                    "name": name,
                    "role": role,
                    "lastMessage": message.body,
                    "created_at": message.created_at,
                }

        latest_thread = max(
            threads_by_participant.values(),
            key=lambda thread: thread["created_at"],
            default=None,
        )
        threads = [
            ConversationThread(
                name=thread["name"],
                lastMessage=thread["lastMessage"],
                time=thread["created_at"].strftime("%I:%M %p"),
                active=thread is latest_thread,
                role=thread["role"],
            )
            for thread in sorted(
                threads_by_participant.values(),
                key=lambda item: item["created_at"],
                reverse=True,
            )
        ]

        return MessagesOverviewResponse(
            conversations=threads,
            messages=[MessageResponse.model_validate(m) for m in messages]
        )

    @staticmethod
    def send_message(db: Session, driver: User, body: str) -> MessageResponse:
        # Save a new message sent by the driver
        new_msg = Message(
            sender_id=driver.id,
            sender_name=driver.full_name,
            sender_role="Driver",
            recipient_id=None, # Dispatcher
            body=body,
            is_read=False
        )
        db.add(new_msg)
        
        # Dispatcher replies automatically or we just log it
        db.commit()
        db.refresh(new_msg)
        return MessageResponse.model_validate(new_msg)

    @staticmethod
    @staticmethod
    def _to_response(t: DriverTask, db: Session) -> DriverTaskResponse:
        status_color = "bg-emerald-100 text-emerald-800 border-emerald-200" if t.status in ["Completed", "In Progress"] else "bg-amber-100 text-amber-800 border-amber-200"
        complaint = db.query(Complaint).filter(Complaint.id == t.complaint_id).first() if t.complaint_id else None
        latest_evidence = db.query(TaskEvidence).filter(TaskEvidence.task_id == t.id).order_by(TaskEvidence.id.desc()).first()
        return DriverTaskResponse(
            id=t.id,
            name=t.location_name,
            status=t.status,
            statusColor=status_color,
            location_name=t.location_name,
            complaint_id=t.complaint_id,
            proof_image_url=t.proof_image_url,
            latitude=complaint.latitude if complaint else None,
            longitude=complaint.longitude if complaint else None,
            rejection_reason=latest_evidence.rejection_reason if latest_evidence and latest_evidence.status == "rejected" else None,
            collected_at=latest_evidence.collected_at.isoformat() if latest_evidence and latest_evidence.collected_at else None,
        )
