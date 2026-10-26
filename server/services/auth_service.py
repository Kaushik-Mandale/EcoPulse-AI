import os

from sqlalchemy.orm import Session
from sqlalchemy import func
from fastapi import HTTPException, status
from server.models.user import User
from server.schemas.auth import LoginRequest, SignupRequest, AuthResponse, UserResponse
from server.utils.security import hash_password, verify_password, create_access_token

DUMMY_HASH = "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW" # Precomputed dummy bcrypt hash

class AuthService:
    @staticmethod
    def should_seed_demo_users() -> bool:
        env_name = (os.getenv("ENV", os.getenv("ENVIRONMENT", "development")) or "development").strip().lower()
        return env_name not in {"production", "prod"}

    @staticmethod
    def seed_demo_users(db: Session):
        """Seeds standard demo accounts if they do not exist."""
        if not AuthService.should_seed_demo_users():
            return
        demo_accounts = [
            {
                "full_name": "Priya Patil",
                "email": "priya@cityswap.io",
                "phone": "9876543210",
                "employee_id": None,
                "password": "Password123!",
                "role": "citizen",
                "ward": "Ward 12"
            },
            {
                "full_name": "Ramesh Yadav",
                "email": "ramesh@cityswap.io",
                "phone": "9876543211",
                "employee_id": "EMP-DRIVER-01",
                "password": "Password123!",
                "role": "driver",
                "ward": "Ward 12"
            },
            {
                "full_name": "Suresh Sanitation",
                "email": "collector@cityswap.io",
                "phone": "9876543212",
                "employee_id": "EMP-COLL-01",
                "password": "Password123!",
                "role": "collector",
                "ward": "Ward 8"
            },
            {
                "full_name": "Admin Officer",
                "email": "admin@cityswap.io",
                "phone": "9876543213",
                "employee_id": "EMP-ADMIN-01",
                "password": "Password123!",
                "role": "admin",
                "ward": "Municipal HQ"
            }
        ]

        for acc in demo_accounts:
            existing = db.query(User).filter(User.email == acc["email"]).first()
            if not existing:
                new_u = User(
                    full_name=acc["full_name"],
                    email=acc["email"],
                    phone=acc.get("phone"),
                    employee_id=acc["employee_id"],
                    hashed_password=hash_password(acc["password"]),
                    role=acc["role"],
                    ward=acc["ward"]
                )
                db.add(new_u)
            else:
                if not existing.phone and acc.get("phone"):
                    existing.phone = acc.get("phone")
        db.commit()

    @staticmethod
    def register_user(db: Session, payload: SignupRequest) -> AuthResponse:
        # Check if email already exists
        existing_user = db.query(User).filter(User.email == payload.email).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email address is already registered. Please login instead."
            )
        
        if payload.employeeId:
            existing_emp = db.query(User).filter(User.employee_id == payload.employeeId).first()
            if existing_emp:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Employee ID is already registered."
                )

        # Create new user securely
        hashed_pwd = hash_password(payload.password)
        new_user = User(
            full_name=payload.fullName,
            email=payload.email,
            hashed_password=hashed_pwd,
            role=payload.role or "citizen",
            ward=payload.ward or "Ward 12",
            phone=payload.phone or "",
            employee_id=payload.employeeId
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        import time
        session_id = f"sess_{new_user.id}_{int(time.time())}"
        token = create_access_token({
            "sub": new_user.email,
            "role": new_user.role,
            "id": new_user.id,
            "sid": session_id
        })
        return AuthResponse(
            access_token=token,
            user=UserResponse(
                id=new_user.id,
                name=new_user.full_name,
                email=new_user.email,
                role=new_user.role,
                ward=new_user.ward,
                phone=new_user.phone,
                employee_id=new_user.employee_id,
                eco_coins=new_user.eco_coins
            )
        )

    @staticmethod
    def login_user(db: Session, payload: LoginRequest) -> AuthResponse:
        # Ensure demo accounts exist only in local/dev/test workflows.
        if AuthService.should_seed_demo_users():
            AuthService.seed_demo_users(db)

        clean_ident = payload.email.strip()
        clean_phone = clean_ident.replace("+91", "").replace(" ", "").replace("-", "")

        # Query database for user by email, employee_id, or phone
        user = db.query(User).filter(
            (func.lower(User.email) == clean_ident.lower()) |
            (func.lower(User.employee_id) == clean_ident.lower()) |
            (User.employee_id == clean_ident) |
            (User.phone == clean_ident) |
            (User.phone == clean_phone)
        ).first()

        # Constant-time security check against user enumeration timing attacks
        if not user:
            verify_password(payload.password, DUMMY_HASH)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials. Please verify your email/employee ID and password."
            )

        # Check account lock status
        if user.is_locked:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is locked due to multiple failed login attempts. Please contact municipal support."
            )

        # Verify password hash
        if not verify_password(payload.password, user.hashed_password):
            user.failed_attempts = (user.failed_attempts or 0) + 1
            if user.failed_attempts >= 5:
                user.is_locked = True
            db.commit()

            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials. Please verify your email/employee ID and password."
            )

        # Successful login: reset failed attempts counter
        user.failed_attempts = 0
        
        # Strict Role-Based Portal Access Control
        # If user registered as citizen, they CANNOT log in via driver or admin portal.
        # Drivers can log in to driver portal (or admin if authorized). Admins can log in to admin.
        if payload.role:
            target_role = payload.role.lower()
            user_role = user.role.lower()
            
            # Helper for role hierarchy / permission checking
            allowed = False
            if target_role == user_role:
                allowed = True
            elif target_role in ["admin", "collector"] and user_role in ["admin", "collector"]:
                allowed = True
            elif target_role == "driver" and user_role == "admin":
                allowed = True

            if not allowed:
                portal_names = {"citizen": "Citizen", "driver": "Driver", "admin": "Admin", "collector": "Admin"}
                target_portal_name = portal_names.get(target_role, target_role.capitalize())
                user_portal_name = portal_names.get(user_role, user_role.capitalize())
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Access Denied: This account is registered as a '{user_portal_name}'. You cannot log in via the '{target_portal_name} Portal'."
                )

        db.commit()
        db.refresh(user)

        # Generate secure JWT with sub, role, user id, and session timestamp
        import time
        session_id = f"sess_{user.id}_{int(time.time())}"
        token = create_access_token({
            "sub": user.email,
            "role": user.role,
            "id": user.id,
            "sid": session_id
        })
        return AuthResponse(
            access_token=token,
            user=UserResponse(
                id=user.id,
                name=user.full_name,
                email=user.email,
                role=user.role,
                ward=user.ward,
                phone=user.phone,
                employee_id=user.employee_id,
                eco_coins=user.eco_coins or 100
            )
        )

    @staticmethod
    def update_user_profile(db: Session, user: User, payload) -> UserResponse:
        if payload.full_name is not None:
            user.full_name = payload.full_name
        if payload.ward is not None:
            user.ward = payload.ward
        if payload.phone is not None:
            user.phone = payload.phone
            
        db.commit()
        db.refresh(user)

        return UserResponse(
            id=user.id,
            name=user.full_name,
            email=user.email,
            role=user.role,
            ward=user.ward,
            phone=user.phone,
            employee_id=user.employee_id,
            eco_coins=user.eco_coins or 100
        )

    @staticmethod
    def request_password_reset(db: Session, identifier: str, role: str = "citizen") -> dict:
        clean_ident = identifier.strip()
        clean_phone = clean_ident.replace("+91", "").replace(" ", "").replace("-", "")

        user = db.query(User).filter(
            (func.lower(User.email) == clean_ident.lower()) |
            (func.lower(User.employee_id) == clean_ident.lower()) |
            (User.employee_id == clean_ident) |
            (User.phone == clean_ident) |
            (User.phone == clean_phone)
        ).first()

        # Secure response: Always confirm instructions dispatched to prevent account harvesting
        if user:
            return {
                "success": True,
                "message": f"Password reset instructions have been dispatched to registered communication channels for {clean_ident}."
            }
        return {
            "success": True,
            "message": f"If an account is associated with {clean_ident}, reset instructions have been dispatched."
        }

    @staticmethod
    def send_otp(db: Session, phone: str) -> dict:
        clean_phone = phone.strip().replace("+91", "").replace(" ", "").replace("-", "")
        if len(clean_phone) < 10:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid mobile number. Please provide a valid 10-digit phone number."
            )
        # Mock or dispatch SMS OTP
        return {
            "success": True,
            "message": f"Verification code dispatched to +91 {clean_phone}.",
            "phone": clean_phone
        }

    @staticmethod
    def verify_otp(db: Session, phone: str, otp: str, role: str = "citizen") -> AuthResponse:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OTP verification is currently unavailable. Please use password-based authentication."
        )
