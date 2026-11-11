import os
import sys

# Ensure project root is in sys.path when deployed with service root 'server'
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
import logging
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from server.database.db import engine, Base, SessionLocal, ensure_complaints_schema, ensure_users_schema
import server.models  # Import all SQLAlchemy models to register them with Base.metadata
from server.routes import health, item, auth, complaint, driver, admin, uploads, whatsapp
from server.services.auth_service import AuthService
from server.utils.config import config, normalize_environment

from contextlib import asynccontextmanager

# Configure structured logging early so all startup messages are visible in Render logs
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

config.validate_production_settings()

# Create database tables automatically if they don't exist
Base.metadata.create_all(bind=engine)

# Apply idempotent startup migrations for tables added after initial schema creation
from server.models.whatsapp_session import ensure_whatsapp_processed_messages_schema, ensure_whatsapp_citizens_schema
ensure_whatsapp_processed_messages_schema(engine)
ensure_whatsapp_citizens_schema(engine)
ensure_complaints_schema(engine)
ensure_users_schema(engine)

@asynccontextmanager
async def lifespan(app: FastAPI):
    config.reload()
    env = normalize_environment(os.getenv("ENV", os.getenv("ENVIRONMENT", config.ENV)))
    from server.database.db import safe_database_url_for_logging, SQLALCHEMY_DATABASE_URL
    logger.info(
        "[STARTUP] EcoPulse AI starting | env=%s | db=%s",
        env,
        safe_database_url_for_logging(SQLALCHEMY_DATABASE_URL),
    )
    if env == "production":
        config.validate_production_settings()

    # Read-only schema compatibility validation for Phase 2 OTP delivery observability
    # and website-generated WhatsApp registration verification
    # (Does NOT mutate database or execute ALTER TABLE at runtime)
    from server.models.mobile_otp import check_mobile_otp_tokens_schema
    from server.models.whatsapp_registration_challenge import check_whatsapp_registration_challenges_schema
    check_mobile_otp_tokens_schema(engine)
    check_whatsapp_registration_challenges_schema(engine)

    db = SessionLocal()
    try:
        if AuthService.should_seed_demo_users():
            AuthService.seed_demo_users(db)
        from sqlalchemy import text
        tables = ['tasks', 'complaints', 'users', 'items', 'notifications', 'fuel_logs', 'whatsapp_citizens', 'whatsapp_processed_messages']
        for t in tables:
            try:
                seq = db.execute(text(f"SELECT pg_get_serial_sequence('{t}', 'id')")).scalar()
                if seq:
                    max_id = db.execute(text(f"SELECT COALESCE(MAX(id), 0) FROM {t}")).scalar()
                    db.execute(text(f"SELECT setval('{seq}', {max_id + 1}, false)"))
            except Exception:
                pass
        db.commit()
    finally:
        db.close()
    yield

app = FastAPI(
    title=config.PROJECT_NAME,
    version=config.VERSION,
    description="Backend API for EcoPulse AI / CITY_SWAP - Full Stack Platform",
    lifespan=lifespan
)

# Canonical production frontend origin
CANONICAL_FRONTEND_ORIGIN = "https://ecopulse-ai-frontend.onrender.com"

# Build allowed CORS origins: preserve configured origins and ensure the
# canonical production frontend origin is always explicitly permitted.
cors_origins: list[str] = [orig.rstrip("/") for orig in config.CORS_ORIGINS]
if CANONICAL_FRONTEND_ORIGIN not in cors_origins:
    cors_origins.append(CANONICAL_FRONTEND_ORIGIN)

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve uploaded media files statically
uploads_dir = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(uploads_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=uploads_dir), name="uploads")

# Register modular routes
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(complaint.router)
app.include_router(driver.router)
app.include_router(admin.router)
app.include_router(item.router)
app.include_router(uploads.router)
app.include_router(whatsapp.router, prefix="/api/whatsapp", tags=["WhatsApp"])

from server.schemas.auth import UserResponse
from server.utils.security import get_current_user
from server.models.user import User

@app.get("/api/my", response_model=UserResponse, tags=["Authentication"])
def get_my_current_user(current_user: User = Depends(get_current_user)):
    """Alias for /api/auth/me returning the authenticated user profile."""
    return UserResponse(
        id=current_user.id,
        name=current_user.full_name,
        email=current_user.email,
        role=current_user.role,
        ward=current_user.ward,
        phone=current_user.phone,
        employee_id=current_user.employee_id,
        eco_coins=current_user.eco_coins or 100
    )

@app.get("/")
def root():
    return {
        "message": f"Welcome to {config.PROJECT_NAME}",
        "docs": "/docs",
        "health": "/api/health"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server.main:app", host="127.0.0.1", port=config.PORT, reload=True)
