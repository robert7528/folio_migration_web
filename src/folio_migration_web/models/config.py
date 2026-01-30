"""Migration configuration Pydantic models."""

from typing import Any, Optional
from pydantic import BaseModel, Field


class FileDefinition(BaseModel):
    """File definition for migration tasks."""

    file_name: str
    discovery_suppressed: bool = False
    staff_suppressed: bool = False


class LibraryInformation(BaseModel):
    """Library configuration matching folio_migration_tools."""

    tenant_id: str = Field(..., alias="tenantId")
    multi_field_delimiter: str = Field(default="<^>", alias="multiFieldDelimiter")
    okapi_url: str = Field(..., alias="okapiUrl")
    okapi_username: str = Field(default="", alias="okapiUsername")
    log_level_debug: bool = Field(default=False, alias="logLevelDebug")
    library_name: str = Field(..., alias="libraryName")
    folio_release: str = Field(default="sunflower", alias="folioRelease")
    add_time_stamp_to_file_names: bool = Field(default=False, alias="addTimeStampToFileNames")
    iteration_identifier: str = Field(..., alias="iterationIdentifier")

    class Config:
        populate_by_name = True


class MigrationTask(BaseModel):
    """Base migration task configuration."""

    name: str
    migration_task_type: str = Field(..., alias="migrationTaskType")

    # Common optional fields
    files: Optional[list[FileDefinition]] = None
    batch_size: Optional[int] = Field(default=None, alias="batchSize")

    class Config:
        populate_by_name = True
        extra = "allow"  # Allow additional task-specific fields


class MigrationConfig(BaseModel):
    """Full migration configuration file model."""

    library_information: LibraryInformation = Field(..., alias="libraryInformation")
    migration_tasks: list[MigrationTask] = Field(..., alias="migrationTasks")

    class Config:
        populate_by_name = True


class ConfigValidationResult(BaseModel):
    """Result of configuration validation."""

    valid: bool
    errors: Optional[list[dict[str, Any]]] = None
    parsed: Optional[dict[str, Any]] = None
