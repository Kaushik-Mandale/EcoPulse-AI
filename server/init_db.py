import os
import sys

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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


def initialize_database():
    env = _guard_initialization_environment()

    # Lazy imports: database engine, models, and sessions are imported ONLY
    # after the environment guard has verified an authorized development/test environment.
    from server.database.db import engine, Base, SessionLocal, safe_database_url_for_logging
    from server.database.target_policy import validate_development_target
    import server.models  # noqa: F401
    from server.services.auth_service import AuthService

    # ENV permission is not sufficient: classify the actual DB target before
    # create_all, compatibility helpers, or any seed query/write.
    validate_development_target(engine, env)

    print("Connecting to database and creating tables...", flush=True)
    print(f"Target Database: {safe_database_url_for_logging(str(engine.url))}", flush=True)

    # Create all tables in database
    Base.metadata.create_all(bind=engine)
    print("Tables created successfully!", flush=True)

    # Seed demo users (only permitted in exact development environment)
    db = SessionLocal()
    try:
        if AuthService.should_seed_demo_users():
            AuthService.seed_demo_users(db)
            print("Demo users seeded successfully!", flush=True)
    except Exception as e:
        print(f"Error seeding demo users: {e}", flush=True)
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    _guard_initialization_environment()
    initialize_database()
