"""Client Pydantic models."""

from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator
import re


class ClientType(str, Enum):
    """Client type enumeration."""

    university = "university"
    public = "public"
    special = "special"
    corporate = "corporate"


class ClientCreate(BaseModel):
    """Input model for creating a new client project."""

    client_code: str = Field(
        ...,
        min_length=2,
        max_length=20,
        description="Unique client code (lowercase, alphanumeric, underscores)",
        examples=["thu", "tpml", "ntl"],
    )
    client_name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Full client name",
        examples=["東海大學圖書館"],
    )
    client_type: ClientType = Field(
        ...,
        description="Client type category",
    )
    folio_url: str = Field(
        ...,
        description="FOLIO Gateway URL",
        examples=["https://folio.example.com"],
    )
    tenant_id: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="FOLIO Tenant ID",
        examples=["fs00001234"],
    )
    pm_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Project Manager name",
    )
    start_date: Optional[date] = Field(
        default=None,
        description="Project start date (defaults to today)",
    )

    @field_validator("client_code")
    @classmethod
    def validate_client_code(cls, v: str) -> str:
        """Validate client code format."""
        if not re.match(r"^[a-z][a-z0-9_]*$", v):
            raise ValueError(
                "Client code must start with lowercase letter and contain only lowercase letters, numbers, and underscores"
            )
        return v

    @field_validator("folio_url")
    @classmethod
    def validate_folio_url(cls, v: str) -> str:
        """Validate and normalize FOLIO URL."""
        v = v.strip().rstrip("/")
        if not v.startswith(("http://", "https://")):
            raise ValueError("FOLIO URL must start with http:// or https://")
        return v


class ClientResponse(BaseModel):
    """Response model for client information."""

    client_code: str
    client_name: str
    client_type: ClientType
    folio_url: str
    tenant_id: str
    pm_name: str
    start_date: Optional[date]
    status: str
    status_message: Optional[str]
    tool_version: Optional[str]
    python_version: Optional[str]
    credentials_set: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ClientListItem(BaseModel):
    """Simplified client model for list view."""

    client_code: str
    client_name: str
    client_type: ClientType
    pm_name: str
    status: str
    credentials_set: bool
    created_at: datetime

    class Config:
        from_attributes = True


class ClientCredentials(BaseModel):
    """FOLIO credentials model."""

    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class ConnectionTestResult(BaseModel):
    """Result of FOLIO connection test."""

    success: bool
    message: str
    folio_version: Optional[str] = None
