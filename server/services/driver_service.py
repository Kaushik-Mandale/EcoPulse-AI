from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from server.models.task import DriverTask
from server.models.complaint import Complaint
from server.models.user import User
from server.models.fuel_log import FuelLog
from server.models.performance import DriverPerformance
from server.models.message import Message
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
        if driver and driver.id:
            query = query.filter((DriverTask.driver_id == driver.id) | (DriverTask.driver_id == None))
            
        tasks = query.order_by(DriverTask.id.asc()).all()
        if not tasks:
            DriverService.seed_default_tasks(db, driver.id if driver else None)
            tasks = db.query(DriverTask).order_by(DriverTask.id.asc()).all()

        return [DriverService._to_response(t) for t in tasks]

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
        if driver:
            is_admin = getattr(driver, "role", "").lower() in ["admin", "collector"]
            if not is_admin and task.driver_id != driver.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access forbidden: You can only modify tasks assigned to you."
                )

        task.status = new_status
        if proof_image:
            task.proof_image_url = proof_image

        # Sync linked complaint status in PostgreSQL
        if task.complaint_id:
            complaint = db.query(Complaint).filter(Complaint.id == task.complaint_id).first()
            if complaint:
                complaint.status = "Completed" if new_status == "Completed" else ("In Progress" if new_status == "In Progress" else "Pending")
                if new_status == "Completed" and complaint.citizen_id:
                    citizen = db.query(User).filter(User.id == complaint.citizen_id).first()
                    if citizen:
                        citizen.eco_coins = (citizen.eco_coins or 100) + 25

        # Award driver eco coins for completing task
        if new_status == "Completed" and driver:
            driver.eco_coins = (driver.eco_coins or 100) + 50

        db.commit()
        db.refresh(task)
        return DriverService._to_response(task)

    @staticmethod
    def get_performance_data(db: Session, driver: User) -> PerformanceOverviewResponse:
        # Check if performance trends exist for this driver, otherwise seed defaults
        perf_records = db.query(DriverPerformance).filter(DriverPerformance.driver_id == driver.id).all()
        if not perf_records:
            DriverService.seed_default_performance(db, driver.id)
            perf_records = db.query(DriverPerformance).filter(DriverPerformance.driver_id == driver.id).all()

        # Build weekly trends chart data
        weekly_trends = []
        days_order = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        for day in days_order:
            record = next((r for r in perf_records if r.date == day), None)
            if record:
                weekly_trends.append(WeeklyTrendBar(
                    day=day,
                    h=f"{int(record.efficiency)}%",
                    active=(day == "Wed"),
                    value=f"{int(record.efficiency)}%" if day == "Wed" else None
                ))
            else:
                weekly_trends.append(WeeklyTrendBar(day=day, h="0%", active=False))

        # Calculate dynamic average safety score and fuel economy
        avg_safety = int(sum(r.safety_score for r in perf_records) / len(perf_records)) if perf_records else 98
        avg_fuel = round(sum(r.fuel_economy for r in perf_records) / len(perf_records), 1) if perf_records else 4.1
        avg_efficiency = int(sum(r.efficiency for r in perf_records) / len(perf_records)) if perf_records else 94

        # Achievements List
        achievements = [
            Achievement(title="Perfect Week", subtitle="100% stop coverage", unlocked=True, icon="Sparkles"),
            Achievement(title="Eco Driver Lvl 3", subtitle="Save 50L fuel", unlocked=True, icon="Activity"),
            Achievement(title="100k Club", subtitle="Drive 100,000 km", unlocked=False, icon="AlertCircle")
        ]

        # Leaderboard
        leaderboard = [
            LeaderboardEntry(rank=1, initials="AS", name="Anita Sharma", points=2100, is_you=False),
            LeaderboardEntry(rank=2, initials="BB", name=driver.full_name, points=driver.eco_coins or 100, is_you=True),
            LeaderboardEntry(rank=3, initials="SJ", name="Suresh Joshi", points=1220, is_you=False)
        ]

        return PerformanceOverviewResponse(
            collection_efficiency=f"{avg_efficiency}%",
            collection_efficiency_pct="+4.2%",
            eco_coins_balance=driver.eco_coins or 100,
            eco_coins_earned=f"{driver.eco_coins - 100 if (driver.eco_coins and driver.eco_coins > 100) else 120} earned",
            fuel_economy=f"{avg_fuel} km/l",
            fuel_economy_pct="-0.2 km/l",
            safety_score=f"{avg_safety}/100",
            safety_score_pct="Top 5%",
            weekly_trends=weekly_trends,
            achievements=achievements,
            leaderboard=leaderboard
        )

    @staticmethod
    def get_fuel_logs(db: Session, driver: User) -> FuelLogsSummaryResponse:
        logs = db.query(FuelLog).filter(FuelLog.driver_id == driver.id).order_by(FuelLog.created_at.desc()).all()
        if not logs:
            DriverService.seed_default_fuel_logs(db, driver.id)
            logs = db.query(FuelLog).filter(FuelLog.driver_id == driver.id).order_by(FuelLog.created_at.desc()).all()

        total_spent = sum(log.cost for log in logs)
        # Average consumption: typical is 3.8 km/L
        avg_consumption = 3.8

        # Current fuel level can be simulated around 62%
        current_fuel_level = 62

        return FuelLogsSummaryResponse(
            logs=[FuelLogResponse.model_validate(log) for log in logs],
            current_fuel_level=current_fuel_level,
            avg_consumption=avg_consumption,
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

        if not messages:
            DriverService.seed_default_messages(db, driver.id)
            messages = db.query(Message).filter(
                (Message.recipient_id == driver.id) | (Message.sender_id == driver.id)
            ).order_by(Message.created_at.asc()).all()

        # Build list of active threads (e.g. Dispatch Center, Fleet Maintenance, District Team Alpha)
        last_dispatch = next((m.body for m in reversed(messages) if m.sender_role == "Dispatcher"), "Avoid Main St due to construction.")
        
        threads = [
            ConversationThread(name="Dispatch Center", lastMessage=last_dispatch, time="10:42 AM", active=True, role="Dispatcher"),
            ConversationThread(name="Fleet Maintenance", lastMessage="Reminder: Vehicle inspection due tomorrow.", time="09:15 AM", active=False, role="Maintenance"),
            ConversationThread(name="District Team Alpha", lastMessage="Good job on the route completion guys.", time="Yesterday", active=False, role="Team")
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
    def seed_default_tasks(db: Session, driver_id: Optional[int] = None):
        seeds = [
            DriverTask(id=1, location_name="1. Green Park, Plot No. 45", status="Completed", route_order=1, driver_id=driver_id),
            DriverTask(id=2, location_name="2. Sai Nagar, Main Road", status="In Progress", route_order=2, driver_id=driver_id),
            DriverTask(id=3, location_name="3. Shanti Apartment", status="Pending", route_order=3, driver_id=driver_id),
            DriverTask(id=4, location_name="4. Market Area, Gate No. 2", status="Pending", route_order=4, driver_id=driver_id),
        ]
        db.add_all(seeds)
        db.commit()

    @staticmethod
    def seed_default_performance(db: Session, driver_id: int):
        perf_data = [
            DriverPerformance(driver_id=driver_id, date="Mon", efficiency=60.0, safety_score=98, fuel_economy=4.1),
            DriverPerformance(driver_id=driver_id, date="Tue", efficiency=75.0, safety_score=95, fuel_economy=4.0),
            DriverPerformance(driver_id=driver_id, date="Wed", efficiency=90.0, safety_score=99, fuel_economy=4.2),
            DriverPerformance(driver_id=driver_id, date="Thu", efficiency=65.0, safety_score=97, fuel_economy=4.1),
            DriverPerformance(driver_id=driver_id, date="Fri", efficiency=80.0, safety_score=98, fuel_economy=4.3),
            DriverPerformance(driver_id=driver_id, date="Sat", efficiency=45.0, safety_score=92, fuel_economy=3.9),
            DriverPerformance(driver_id=driver_id, date="Sun", efficiency=30.0, safety_score=90, fuel_economy=3.8),
        ]
        db.add_all(perf_data)
        db.commit()

    @staticmethod
    def seed_default_fuel_logs(db: Session, driver_id: int):
        import datetime
        logs = [
            FuelLog(driver_id=driver_id, odometer=45120, liters=45.0, cost=4200.0, created_at=datetime.datetime.utcnow() - datetime.timedelta(days=1)),
            FuelLog(driver_id=driver_id, odometer=44850, liters=50.2, cost=4650.0, created_at=datetime.datetime.utcnow() - datetime.timedelta(days=7)),
            FuelLog(driver_id=driver_id, odometer=44500, liters=38.5, cost=3600.0, created_at=datetime.datetime.utcnow() - datetime.timedelta(days=15)),
        ]
        db.add_all(logs)
        db.commit()

    @staticmethod
    def seed_default_messages(db: Session, driver_id: int):
        import datetime
        msgs = [
            Message(
                sender_name="Dispatch Center",
                sender_role="Dispatcher",
                recipient_id=driver_id,
                body="Good morning Bhavesh. Your route for today has been loaded. Ward 12 looks clear, but expect heavy traffic near Sector 4 around 11 AM.",
                created_at=datetime.datetime.utcnow() - datetime.timedelta(hours=2)
            ),
            Message(
                sender_id=driver_id,
                sender_name="Bhavesh Burad",
                sender_role="Driver",
                recipient_id=None,
                body="Copy that. Starting route now. Truck #04 fueled and ready.",
                created_at=datetime.datetime.utcnow() - datetime.timedelta(hours=1.9)
            ),
            Message(
                sender_name="Dispatch Center",
                sender_role="Dispatcher",
                recipient_id=driver_id,
                body="Route update: Avoid Main St due to construction. Next stop re-routed to 2nd Avenue.",
                created_at=datetime.datetime.utcnow() - datetime.timedelta(minutes=15)
            )
        ]
        db.add_all(msgs)
        db.commit()

    @staticmethod
    def _to_response(t: DriverTask) -> DriverTaskResponse:
        status_color = "bg-emerald-100 text-emerald-800 border-emerald-200" if t.status in ["Completed", "In Progress"] else "bg-amber-100 text-amber-800 border-amber-200"
        return DriverTaskResponse(
            id=t.id,
            name=t.location_name,
            status=t.status,
            statusColor=status_color,
            location_name=t.location_name,
            complaint_id=t.complaint_id,
            proof_image_url=t.proof_image_url
        )

