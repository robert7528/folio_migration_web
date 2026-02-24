"""Database connection and session management."""

from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.declarative import declarative_base

from ..config import get_settings

settings = get_settings()

# Ensure data directory exists
db_path = Path(settings.database_url.replace("sqlite:///", ""))
db_path.parent.mkdir(parents=True, exist_ok=True)

# Create engine
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},  # SQLite specific
    echo=settings.debug,
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()


def get_db() -> Session:
    """Dependency to get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database tables."""
    from . import models  # noqa: F401
    Base.metadata.create_all(bind=engine)

    # Run migrations for new columns
    _run_migrations()


def _run_migrations():
    """Add new columns to existing tables (SQLite doesn't support ALTER TABLE well)."""
    from sqlalchemy import text

    migrations = [
        # Add merged_count column to executions table
        ("executions", "merged_count", "ALTER TABLE executions ADD COLUMN merged_count INTEGER DEFAULT 0"),
        # Add pre_execution_count for BatchPoster count validation
        ("executions", "pre_execution_count", "ALTER TABLE executions ADD COLUMN pre_execution_count INTEGER"),
        # Add validation_type to distinguish record vs count_check validations
        ("validations", "validation_type", "ALTER TABLE validations ADD COLUMN validation_type VARCHAR(20) DEFAULT 'record'"),
        # Add smtp_original_host for SMTP toggle feature
        ("clients", "smtp_original_host", "ALTER TABLE clients ADD COLUMN smtp_original_host TEXT"),
    ]

    with engine.connect() as conn:
        for table, column, sql in migrations:
            # Check if column exists
            result = conn.execute(text(f"PRAGMA table_info({table})"))
            columns = [row[1] for row in result.fetchall()]
            if column not in columns:
                try:
                    conn.execute(text(sql))
                    conn.commit()
                except Exception:
                    pass  # Column might already exist
