"""Application configuration."""

from pathlib import Path
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    app_name: str = "FOLIO Migration Web"
    app_env: str = "development"
    debug: bool = True

    # Server
    host: str = "127.0.0.1"
    port: int = 8000
    root_path: str = ""  # Set to "/folio" when behind nginx proxy

    # Database
    database_url: str = "sqlite:///./data/migration.db"

    # Clients directory
    clients_dir: Path = Path("./clients")

    # Template repository
    template_repo_url: str = "https://github.com/FOLIO-FSE/migration_repo_template.git"

    # Encryption
    encryption_key: str | None = None

    # File upload
    max_upload_size_mb: int = 500
    allowed_extensions: str = ".mrc,.marc,.json,.csv,.tsv,.txt,.xml"

    @property
    def max_upload_size_bytes(self) -> int:
        """Maximum upload size in bytes."""
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def allowed_extensions_list(self) -> list[str]:
        """List of allowed file extensions."""
        return [ext.strip() for ext in self.allowed_extensions.split(",")]

    def get_client_dir(self, client_code: str) -> Path:
        """Get the directory for a specific client."""
        return self.clients_dir / client_code


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
