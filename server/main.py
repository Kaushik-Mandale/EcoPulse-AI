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
from server.database.db import engine, SessionLocal
from server.database.initialization import (
    initialize_database,
    resynchronize_sequences,
    schema_mutation_allowed,
)
from server.database.target_policy import validate_development_target
import server.models  # Import all SQLAlchemy models to register them with Base.metadata
from server.routes import health, item, auth, complaint, driver, admin, collector, uploads, whatsapp
from server.services.auth_service import AuthService
from server.utils.config import config, normalize_environment, get_environment

from contextlib import asynccontextmanager

# Configure structured logging early so all startup messages are visible in Render logs
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Fail-closed ENV validation — must happen before application startup.
# Raises RuntimeError if ENV is unset, unknown, or if ENV/ENVIRONMENT conflict.
# Note: Zero database operations or connections occur at module import time.
# ---------------------------------------------------------------------------
try:
    _startup_environment = get_environment()
except RuntimeError as _env_err:
    raise RuntimeError(
        f"[STARTUP] Environment configuration rejected: {_env_err}"
    ) from _env_err

@asynccontextmanager
async def lifespan(app: FastAPI):
    config.reload()
    # Read the validated environment dynamically so that test monkeypatching
    # is accurately reflected during application lifespan execution.
    try:
        env = get_environment()
    except RuntimeError:
        env = normalize_environment(os.getenv("ENV") or os.getenv("ENVIRONMENT") or _startup_environment)

    from server.database.db import (
        safe_database_url_for_logging,
        SQLALCHEMY_DATABASE_URL,
        validate_database_connection,
    )
    # Reject a mismatched development environment/database URL before even the
    # startup connectivity probe. Production/staging keep the read-only path.
    if schema_mutation_allowed(env):
        validate_development_target(engine, env)
    logger.info(
        "[STARTUP] EcoPulse AI starting | env=%s | db=%s",
        env,
        safe_database_url_for_logging(SQLALCHEMY_DATABASE_URL),
    )

    # 1. Explicit database connectivity validation (startup operation, never at import time)
    validate_database_connection(engine)

    # 2. Production settings validation
    if env == "production":
        config.validate_production_settings()

    # 3. Database initialization policy (runs exactly once during lifespan startup):
    # - development/dev/local/test/testing: create/patch schema from ORM models.
    # - production/staging: verification-only read check; fails fast if objects missing.
    initialize_database(engine, env)

    # 4. Development demo seeding and sequence resynchronization
    db = SessionLocal()
    try:
        if AuthService.should_seed_demo_users():
            AuthService.seed_demo_users(db)
        resynchronize_sequences(db, env)
    finally:
        db.close()
    yield

app = FastAPI(
    title=config.PROJECT_NAME,
    version=config.VERSION,
    description="Backend API for EcoPulse AI - Smart Civic & Sustainability Ecosystem",
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
app.include_router(collector.router)
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
        login_id=current_user.login_id,
        eco_coins=current_user.eco_coins if current_user.eco_coins is not None else 0,
        is_super_admin=bool(current_user.is_super_admin),
        account_status=current_user.account_status,
        mfa_enabled=bool(current_user.mfa_enabled),
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
