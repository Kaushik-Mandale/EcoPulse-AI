"""
Database initialization and seeding script for CITY_SWAP / EcoPulse AI.
Creates all database tables and seeds rich initial records for Users, Complaints, Tasks, and Swap Items.
"""

import os
import sys

# Ensure server module path is importable
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from server.utils.config import get_environment, is_local_or_test_environment


def _guard_initialization_environment() -> str:
    """Fail closed: only explicitly authorized development/test environments may initialize/seed."""
    try:
        env = get_environment()
    except RuntimeError as exc:
        raise RuntimeError(
            f"Database initialization rejected: {exc}"
        ) from exc
    if not is_local_or_test_environment(env):
        raise RuntimeError(
            f"Database initialization and demo seeding is strictly prohibited in environment {env!r}. "
            "Only explicit development or test environments may execute this script."
        )
    return env


def init_and_seed_db():
    _guard_initialization_environment()

    # Lazy imports after environment guard verification:
    from server.database.db import engine, Base, SessionLocal
    from server.models.user import User
    from server.models.complaint import Complaint
    from server.models.task import DriverTask
    from server.models.item import Item
    from server.utils.security import hash_password
    from server.database.target_policy import validate_development_target

    # This script inserts demo identities and sample listings; validate the
    # resolved target before table creation or any inspection/mutation.
    from server.utils.config import get_environment
    validate_development_target(engine, get_environment())

    print("Creating all database tables...")
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    try:
        # Check if DB already populated
        existing_users_count = db.query(User).count()
        if existing_users_count > 0:
            print(f"Database already initialized with {existing_users_count} users. Updating seed data...")
        
        # 1. Seed Users
        demo_users = [
            {
                "full_name": "Priya Patil",
                "email": "priya@cityswap.io",
                "employee_id": None,
                "password": "Password123!",
                "role": "citizen",
                "ward": "Ward 12",
                "eco_coins": 150
            },
            {
                "full_name": "Rahul Sharma",
                "email": "rahul@cityswap.io",
                "employee_id": None,
                "password": "Password123!",
                "role": "citizen",
                "ward": "Ward 8",
                "eco_coins": 200
            },
            {
                "full_name": "Ramesh Yadav",
                "email": "ramesh@cityswap.io",
                "employee_id": "EMP-DRIVER-01",
                "password": "Password123!",
                "role": "driver",
                "ward": "Ward 12",
                "eco_coins": 100
            },
            {
                "full_name": "Suresh Kumar",
                "email": "suresh@cityswap.io",
                "employee_id": "EMP-DRIVER-02",
                "password": "Password123!",
                "role": "driver",
                "ward": "Ward 8",
                "eco_coins": 100
            },
            {
                "full_name": "Ajay Patel",
                "email": "collector@cityswap.io",
                "employee_id": "EMP-COLL-01",
                "password": "Password123!",
                "role": "collector",
                "ward": "Ward 4",
                "eco_coins": 100
            },
            {
                "full_name": "Admin Officer",
                "email": "admin@cityswap.io",
                "employee_id": "EMP-ADMIN-01",
                "password": "Password123!",
                "role": "admin",
                "ward": "Municipal HQ",
                "eco_coins": 500
            }
        ]

        created_users = {}
        for udata in demo_users:
            usr = db.query(User).filter(User.email == udata["email"]).first()
            if not usr:
                usr = User(
                    full_name=udata["full_name"],
                    email=udata["email"],
                    employee_id=udata["employee_id"],
                    hashed_password=hash_password(udata["password"]),
                    role=udata["role"],
                    ward=udata["ward"],
                    eco_coins=udata["eco_coins"],
                    is_active=True,
                    is_verified=True,
                    account_status="active",
                )
                db.add(usr)
                db.commit()
                db.refresh(usr)
            created_users[udata["email"]] = usr

        print(f"Users table seeded with {len(created_users)} core user roles.")

        # 2. Seed Complaints
        if db.query(Complaint).count() == 0:
            complaints_data = [
                Complaint(
                    tracking_number="EP-2026-00123",
                    citizen_id=created_users.get("priya@cityswap.io").id if created_users.get("priya@cityswap.io") else None,
                    ward="Ward 12",
                    location_address="Green Park, Plot No. 45",
                    latitude=19.0760,
                    longitude=72.8777,
                    waste_type="Mixed Waste",
                    description="Overflowing bin near public park area.",
                    status="In Progress",
                    assigned_driver_name="Ramesh Yadav",
                    assigned_driver_id=created_users.get("ramesh@cityswap.io").id if created_users.get("ramesh@cityswap.io") else None,
                    ai_status="Verified",
                    ai_confidence=0.98
                ),
                Complaint(
                    tracking_number="EP-2026-00122",
                    citizen_id=created_users.get("rahul@cityswap.io").id if created_users.get("rahul@cityswap.io") else None,
                    ward="Ward 8",
                    location_address="Sai Nagar, Main Road",
                    latitude=19.0800,
                    longitude=72.8800,
                    waste_type="Garbage Overflow",
                    description="Commercial street bin overflowing onto sidewalk.",
                    status="Pending",
                    assigned_driver_name="Suresh Kumar",
                    assigned_driver_id=created_users.get("suresh@cityswap.io").id if created_users.get("suresh@cityswap.io") else None,
                    ai_status="Verified",
                    ai_confidence=0.94
                ),
                Complaint(
                    tracking_number="EP-2026-00121",
                    citizen_id=created_users.get("priya@cityswap.io").id if created_users.get("priya@cityswap.io") else None,
                    ward="Ward 4",
                    location_address="Market Area, Gate No. 2",
                    latitude=19.0850,
                    longitude=72.8850,
                    waste_type="Plastic Waste",
                    description="Plastic bottle packaging waste reported by vendor.",
                    status="Completed",
                    assigned_driver_name="Ajay Patel",
                    ai_status="Verified",
                    ai_confidence=0.99
                ),
                Complaint(
                    tracking_number="EP-2026-00120",
                    citizen_id=created_users.get("rahul@cityswap.io").id if created_users.get("rahul@cityswap.io") else None,
                    ward="Ward 10",
                    location_address="Shanti Apartment Complex",
                    latitude=19.0900,
                    longitude=72.8900,
                    waste_type="E-Waste",
                    description="Electronic components and discarded monitors.",
                    status="Pending",
                    assigned_driver_name="Unassigned",
                    ai_status="Verified",
                    ai_confidence=0.96
                )
            ]
            db.add_all(complaints_data)
            db.commit()
            print("Complaints table seeded successfully.")

        # 3. Seed Driver Tasks
        if db.query(DriverTask).count() == 0:
            tasks_data = [
                DriverTask(
                    location_name="1. Green Park, Plot No. 45",
                    status="Completed",
                    route_order=1
                ),
                DriverTask(
                    location_name="2. Sai Nagar, Main Road",
                    status="In Progress",
                    route_order=2
                ),
                DriverTask(
                    location_name="3. Shanti Apartment",
                    status="Pending",
                    route_order=3
                ),
                DriverTask(
                    location_name="4. Market Area, Gate No. 2",
                    status="Pending",
                    route_order=4
                )
            ]
            db.add_all(tasks_data)
            db.commit()
            print("Tasks table seeded successfully.")

        # 4. Seed Swap Items
        if db.query(Item).count() == 0:
            items_data = [
                Item(
                    owner_id=created_users.get("priya@cityswap.io").id if created_users.get("priya@cityswap.io") else None,
                    owner_name="Priya Patil",
                    title="Vintage Bicycle",
                    category="Transportation",
                    offered_city="Mumbai",
                    desired_city="Pune",
                    description="Restored 1980s road bike in excellent condition.",
                    status="Available"
                ),
                Item(
                    owner_id=created_users.get("rahul@cityswap.io").id if created_users.get("rahul@cityswap.io") else None,
                    owner_name="Rahul Sharma",
                    title="Apartment Stay (1 Week)",
                    category="Housing",
                    offered_city="Delhi",
                    desired_city="Bangalore",
                    description="Cozy 1BR apartment in Indiranagar available for exchange.",
                    status="Available"
                ),
                Item(
                    owner_id=created_users.get("admin@cityswap.io").id if created_users.get("admin@cityswap.io") else None,
                    owner_name="Elena",
                    title="DSLR Camera Kit",
                    category="Electronics",
                    offered_city="Berlin",
                    desired_city="Barcelona",
                    description="Canon DSLR with 18-55mm & 50mm lenses.",
                    status="Available"
                )
            ]
            db.add_all(items_data)
            db.commit()
            print("Swap Items table seeded successfully.")

        print("\nSUCCESS: All database tables created and seeded!")

    except Exception as e:
        db.rollback()
        print(f"Error seeding database: {e}")
        raise e
    finally:
        db.close()

if __name__ == "__main__":
    _guard_initialization_environment()
    init_and_seed_db()
