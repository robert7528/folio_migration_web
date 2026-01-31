"""SQLAlchemy database models."""

from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text, Boolean, Integer, Float, ForeignKey
from sqlalchemy.orm import relationship

from .database import Base


class Client(Base):
    """Client project database model."""

    __tablename__ = "clients"

    client_code = Column(String(20), primary_key=True, index=True)
    client_name = Column(String(200), nullable=False)
    client_type = Column(String(20), nullable=False)
    folio_url = Column(String(500), nullable=False)
    tenant_id = Column(String(100), nullable=False)
    pm_name = Column(String(100), nullable=False)
    start_date = Column(DateTime, nullable=True)

    # Status: created, initializing, ready, error
    status = Column(String(20), default="created")
    status_message = Column(Text, nullable=True)

    # Environment info
    tool_version = Column(String(50), nullable=True)
    python_version = Column(String(50), nullable=True)

    # Encrypted credentials
    credentials_set = Column(Boolean, default=False)
    encrypted_username = Column(Text, nullable=True)
    encrypted_password = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # Notes
    notes = Column(Text, nullable=True)

    def __repr__(self):
        return f"<Client {self.client_code}: {self.client_name}>"


class Execution(Base):
    """Task execution history model."""

    __tablename__ = "executions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    client_code = Column(String(20), ForeignKey("clients.client_code"), nullable=False, index=True)

    # Task information
    task_name = Column(String(100), nullable=False)  # e.g., "transform_bibs"
    task_type = Column(String(100), nullable=False)  # e.g., "BibsTransformer"
    iteration = Column(String(100), nullable=False)  # e.g., "thu_migration"

    # Status: pending, running, completed, failed, cancelled
    status = Column(String(20), default="pending", index=True)

    # Progress tracking
    total_records = Column(Integer, default=0)
    processed_records = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    progress_percent = Column(Float, default=0.0)

    # Timing
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)

    # Output
    log_file = Column(String(500), nullable=True)  # Path to log file
    result_summary = Column(Text, nullable=True)  # JSON summary
    error_message = Column(Text, nullable=True)

    # Process info
    pid = Column(Integer, nullable=True)  # Process ID for cancellation

    # Timestamps
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self):
        return f"<Execution {self.id}: {self.task_name} ({self.status})>"
