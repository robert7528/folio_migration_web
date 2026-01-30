"""SQLAlchemy database models."""

from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text, Boolean

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
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Notes
    notes = Column(Text, nullable=True)

    def __repr__(self):
        return f"<Client {self.client_code}: {self.client_name}>"
