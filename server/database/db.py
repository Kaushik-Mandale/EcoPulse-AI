import logging
import os
from typing import Optional

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker, declarative_base

logger = logging.getLogger(__name__)

# Load environment variables explicitly from server/.env and root .env
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
server_env = os.path.join(base_dir, ".env")
root_env = os.path.join(os.path.dirname(base_dir), ".env")

if os.path.exists(server_env):
    load_dotenv(server_env)
if os.path.exists(root_env):
    load_dotenv(root_env)
load_dotenv()


def normalize_environment(value: Optional[str]) -> str:
    return (value or "").strip().lower()


def get_database_url() -> str:
    raw_url = (os.getenv("DATABASE_URL") or "").strip()
    env_name = normalize_environment(os.getenv("ENV", os.getenv("ENVIRONMENT", "development")))

    if not raw_url:
        if env_name == "production":
            raise RuntimeError("CRITICAL CONFIGURATION ERROR: DATABASE_URL is required in production mode.")
        return "sqlite:///./ecopulse.db"

    normalized = raw_url
    if normalized.startswith("postgresql+psycopg://"):
        normalized = normalized.replace("postgresql+psycopg://", "postgresql+psycopg2://", 1)
    elif normalized.startswith("postgres://"):
        normalized = normalized.replace("postgres://", "postgresql://", 1)

    if normalized.startswith("sqlite"):
        if env_name == "production":
            raise RuntimeError("CRITICAL CONFIGURATION ERROR: SQLite is not allowed in production; set DATABASE_URL to a PostgreSQL connection string.")
        return normalized

    if normalized.startswith(("postgresql://", "postgresql+psycopg2://")):
        try:
            import psycopg2  # noqa: F401
        except ModuleNotFoundError:
            if env_name == "production":
                raise RuntimeError("CRITICAL CONFIGURATION ERROR: PostgreSQL driver psycopg2 is required in production but is not installed.")
            return "sqlite:///./ecopulse.db"

    return normalized


def safe_database_url_for_logging(database_url: str) -> str:
    try:
        parsed = make_url(database_url)
        return f"{parsed.drivername}://***"
    except Exception:
        return "<invalid-database-url>"


def validate_database_connection(engine) -> None:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:
        url = safe_database_url_for_logging(str(engine.url))
        raise RuntimeError(
            f"Database connectivity validation failed for {url} ({type(exc).__name__})."
        ) from None


SQLALCHEMY_DATABASE_URL = get_database_url()
connect_args = {"check_same_thread": False} if SQLALCHEMY_DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
)
validate_database_connection(engine)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def ensure_complaints_schema(engine) -> None:
    """
    Idempotent startup migration: ensures the `complaints` table has the
    `whatsapp_citizen_id` column and its index.

    This column was added to the SQLAlchemy model after the initial Neon
    schema was created. The `ADD COLUMN IF NOT EXISTS` syntax is safe to
    call on every startup — it is a no-op when the column already exists.

    Uses raw DDL rather than Alembic to stay consistent with the existing
    inline-migration approach used by ensure_whatsapp_processed_messages_schema().
    """
    from sqlalchemy import inspect
    try:
        insp = inspect(engine)
        if 'complaints' not in insp.get_table_names():
            # Table does not exist yet — create_all will handle it.
            return
        existing_cols = {col['name'] for col in insp.get_columns('complaints')}
        with engine.connect() as conn:
            if 'whatsapp_citizen_id' not in existing_cols:
                logger.info(
                    "[SCHEMA] Adding missing column complaints.whatsapp_citizen_id"
                )
                col_clause = (
                    "ADD COLUMN whatsapp_citizen_id INTEGER REFERENCES whatsapp_citizens(id) ON DELETE SET NULL"
                    if engine.dialect.name == "sqlite"
                    else "ADD COLUMN IF NOT EXISTS whatsapp_citizen_id INTEGER REFERENCES whatsapp_citizens(id) ON DELETE SET NULL"
                )
                conn.execute(text(f"ALTER TABLE complaints {col_clause}"))
                conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_complaints_whatsapp_citizen_id "
                    "ON complaints (whatsapp_citizen_id)"
                ))
                conn.commit()
                logger.info(
                    "[SCHEMA] complaints.whatsapp_citizen_id added successfully."
                )
    except Exception as exc:
        logger.warning(
            "[SCHEMA] complaints schema check warning: %s", type(exc).__name__
        )


def ensure_users_schema(engine) -> None:
    """
    Idempotent startup migration: ensures the `users` table supports mobile-first OTP:
    - `email` column is nullable
    - `hashed_password` column is nullable
    - unique index on `phone`
    - `mobile_otp_tokens` table exists
    """
    from server.models.mobile_otp import MobileOtpToken
    try:
        MobileOtpToken.__table__.create(engine, checkfirst=True)
    except Exception as exc:
        logger.warning("[SCHEMA] MobileOtpToken table check warning: %s", type(exc).__name__)

    if engine.dialect.name == "sqlite":
        try:
            with engine.connect() as conn:
                table_info = conn.execute(text("PRAGMA table_info(users)")).fetchall()
                email_col = next((c for c in table_info if c[1] == "email"), None)
                if email_col and email_col[3] == 1:
                    conn.execute(text("PRAGMA foreign_keys=OFF;"))
                    conn.execute(text("""
                        CREATE TABLE users_new (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            full_name VARCHAR(100) NOT NULL,
                            email VARCHAR(100),
                            employee_id VARCHAR(50),
                            hashed_password VARCHAR(255),
                            role VARCHAR(20) NOT NULL,
                            ward VARCHAR(50),
                            phone VARCHAR(20),
                            eco_coins INTEGER DEFAULT 100,
                            is_active BOOLEAN DEFAULT 1,
                            failed_attempts INTEGER DEFAULT 0,
                            is_locked BOOLEAN DEFAULT 0,
                            created_at DATETIME,
                            updated_at DATETIME
                        );
                    """))
                    conn.execute(text("INSERT INTO users_new SELECT * FROM users;"))
                    conn.execute(text("DROP TABLE users;"))
                    conn.execute(text("ALTER TABLE users_new RENAME TO users;"))
                    conn.execute(text("PRAGMA foreign_keys=ON;"))
                    conn.commit()
                    logger.info("[SCHEMA] SQLite users table migrated to nullable email/hashed_password.")
        except Exception as exc:
            logger.warning("[SCHEMA] SQLite users schema check warning: %s", type(exc).__name__)

    elif engine.dialect.name == "postgresql":
        try:
            with engine.connect() as conn:
                try:
                    conn.execute(text("ALTER TABLE users ALTER COLUMN email DROP NOT NULL;"))
                    conn.commit()
                except Exception:
                    pass
                try:
                    conn.execute(text("ALTER TABLE users ALTER COLUMN hashed_password DROP NOT NULL;"))
                    conn.commit()
                except Exception:
                    pass
                try:
                    conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_users_phone ON users(phone) WHERE phone IS NOT NULL AND phone != '';"))
                    conn.commit()
                except Exception:
                    pass
            logger.info("[SCHEMA] users mobile-first schema verified successfully.")
        except Exception as exc:
            logger.warning("[SCHEMA] users schema check warning: %s", type(exc).__name__)


def get_db():
    """Dependency that provides a database session to FastAPI routes."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
