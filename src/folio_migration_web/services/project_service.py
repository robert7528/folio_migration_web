"""Project creation and management service.

This module replicates the functionality of setup_client.sh for creating
new client migration projects.
"""

import json
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Optional

from ..config import get_settings
from ..models.client import ClientCreate
from .folder_service import create_iteration_folders
from .config_service import get_config_service

settings = get_settings()


class ProjectService:
    """Service for managing client migration projects."""

    def __init__(self, clients_dir: Path | None = None):
        """Initialize with clients directory."""
        self.clients_dir = clients_dir or settings.clients_dir
        self.clients_dir.mkdir(parents=True, exist_ok=True)

    def get_client_path(self, client_code: str) -> Path:
        """Get the path to a client's project directory."""
        return self.clients_dir / client_code

    def client_exists(self, client_code: str) -> bool:
        """Check if a client project already exists."""
        return self.get_client_path(client_code).exists()

    def create_project(
        self,
        client: ClientCreate,
        skip_venv: bool = False,
        skip_git_clone: bool = False,
    ) -> dict:
        """
        Create a new client migration project.

        Steps:
        1. Clone migration_repo_template
        2. Initialize Git
        3. Create virtual environment
        4. Install folio_migration_tools
        5. Create .env
        6. Create CLIENT_INFO.md
        7. Create configuration files (library_config.json, task configs, mapping templates)
        8. Create folder structure
        9. Update .gitignore

        Args:
            client: Client creation data
            skip_venv: Skip virtual environment creation (for testing)
            skip_git_clone: Skip git clone (use local copy instead)

        Returns:
            Dictionary with creation status and details
        """
        client_path = self.get_client_path(client.client_code)

        if client_path.exists():
            raise ValueError(f"Client project '{client.client_code}' already exists")

        result = {
            "client_code": client.client_code,
            "path": str(client_path),
            "steps": [],
            "tool_version": None,
            "python_version": None,
        }

        try:
            # Step 1: Clone or create project directory
            if skip_git_clone:
                client_path.mkdir(parents=True, exist_ok=True)
                result["steps"].append({"step": 1, "name": "create_directory", "status": "success"})
            else:
                self._clone_template(client_path)
                result["steps"].append({"step": 1, "name": "clone_template", "status": "success"})

            # Step 2: Initialize Git
            self._init_git(client_path)
            result["steps"].append({"step": 2, "name": "init_git", "status": "success"})

            # Step 3 & 4: Virtual environment and install tools
            if not skip_venv:
                self._create_venv(client_path)
                result["steps"].append({"step": 3, "name": "create_venv", "status": "success"})

                tool_version = self._install_tools(client_path)
                result["tool_version"] = tool_version
                result["python_version"] = f"{sys.version_info.major}.{sys.version_info.minor}"
                result["steps"].append({"step": 4, "name": "install_tools", "status": "success"})
            else:
                result["steps"].append({"step": 3, "name": "create_venv", "status": "skipped"})
                result["steps"].append({"step": 4, "name": "install_tools", "status": "skipped"})

            # Step 5: Create .env
            self._create_env_file(client_path, client.client_name)
            result["steps"].append({"step": 5, "name": "create_env", "status": "success"})

            # Step 6: Create CLIENT_INFO.md
            start_date = client.start_date or date.today()
            self._create_client_info(client_path, client, start_date, result.get("tool_version"))
            result["steps"].append({"step": 6, "name": "create_client_info", "status": "success"})

            # Step 7: Create configuration files
            self._create_config(client_path, client)
            result["steps"].append({"step": 7, "name": "create_config", "status": "success"})

            # Step 8: Create folder structure
            iteration_name = f"{client.client_code}_migration"
            create_iteration_folders(client_path, iteration_name)
            result["steps"].append({"step": 8, "name": "create_folders", "status": "success"})

            # Step 9: Update .gitignore
            self._update_gitignore(client_path)
            result["steps"].append({"step": 9, "name": "update_gitignore", "status": "success"})

            result["status"] = "success"

        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)
            # Cleanup on failure
            if client_path.exists():
                import shutil
                shutil.rmtree(client_path, ignore_errors=True)

        return result

    def _clone_template(self, client_path: Path):
        """Clone the migration template repository."""
        subprocess.run(
            ["git", "clone", settings.template_repo_url, str(client_path)],
            check=True,
            capture_output=True,
            text=True,
        )

    def _init_git(self, client_path: Path):
        """Initialize a fresh Git repository."""
        git_dir = client_path / ".git"
        if git_dir.exists():
            import shutil
            shutil.rmtree(git_dir)

        subprocess.run(
            ["git", "init"],
            cwd=client_path,
            check=True,
            capture_output=True,
            text=True,
        )

    def _create_venv(self, client_path: Path):
        """Create Python virtual environment using uv."""
        subprocess.run(
            ["uv", "venv", ".venv", "--python", "3.13"],
            cwd=client_path,
            check=True,
            capture_output=True,
            text=True,
        )

    def _install_tools(self, client_path: Path) -> Optional[str]:
        """Install folio_migration_tools and return version."""
        # Use uv pip to install into the venv
        subprocess.run(
            ["uv", "pip", "install", "folio_migration_tools", "--python", str(client_path / ".venv")],
            cwd=client_path,
            check=True,
            capture_output=True,
            text=True,
        )

        # Try to get version
        try:
            if sys.platform == "win32":
                tool_path = client_path / ".venv" / "Scripts" / "folio-migration-tools"
            else:
                tool_path = client_path / ".venv" / "bin" / "folio-migration-tools"

            result = subprocess.run(
                [str(tool_path), "--version"],
                capture_output=True,
                text=True,
            )
            # Extract version from output
            import re
            match = re.search(r"(\d+\.\d+\.\d+)", result.stdout + result.stderr)
            if match:
                return match.group(1)
        except Exception:
            pass

        return None

    def _create_env_file(self, client_path: Path, client_name: str):
        """Create .env file for credentials."""
        env_content = f"""# {client_name} FOLIO Credentials
# These will be set via the web interface
USERNAME=
PASSWORD=
"""
        env_path = client_path / ".env"
        env_path.write_text(env_content, encoding="utf-8")

    def _create_client_info(
        self,
        client_path: Path,
        client: ClientCreate,
        start_date: date,
        tool_version: Optional[str],
    ):
        """Create CLIENT_INFO.md documentation file."""
        content = f"""# {client.client_name} - FOLIO Migration Project

## Client Information
- **Client Code**: {client.client_code}
- **Client Name**: {client.client_name}
- **Client Type**: {client.client_type.value}
- **Project Manager**: {client.pm_name}
- **Project Start Date**: {start_date.isoformat()}

## FOLIO Environment
- **Gateway URL**: {client.folio_url}
- **Tenant ID**: {client.tenant_id}
- **Tool Version**: folio_migration_tools {tool_version or 'N/A'}

## Project Status
- [ ] Requirements Confirmed
- [ ] Environment Setup Complete
- [ ] Test Migration
- [ ] Production Migration
- [ ] Verification Complete
- [ ] Project Closed

## Contact Information
- **Client Contact**:
- **Email**:
- **Phone**:

## Important Dates
- Project Start: {start_date.isoformat()}
- Test Migration:
- Production Migration:
- Acceptance Date:

## Notes

"""
        info_path = client_path / "CLIENT_INFO.md"
        info_path.write_text(content, encoding="utf-8")

    def _create_config(self, client_path: Path, client: ClientCreate):
        """Create all configuration files using ConfigService."""
        config_service = get_config_service(client_path)
        iteration_id = f"{client.client_code}_migration"

        # Generate library config (shared settings)
        config_service.generate_library_config(
            client_name=client.client_name,
            tenant_id=client.tenant_id,
            folio_url=client.folio_url,
            iteration_id=iteration_id,
        )

        # Generate all task configs
        config_service.generate_all_task_configs()

        # Generate mapping file templates
        config_service.generate_mapping_templates()

        # Enable bibs task by default
        config_service.enable_task("bibs", True)

        # Generate combined config for CLI
        config_service.generate_combined_config()

    def _update_gitignore(self, client_path: Path):
        """Update .gitignore with client-specific entries."""
        gitignore_additions = """
# Client-specific ignores
.env
*.env
logs/
iterations/*/results/
iterations/*/reports/
CLIENT_INFO.md
.venv/
"""
        gitignore_path = client_path / ".gitignore"
        if gitignore_path.exists():
            existing = gitignore_path.read_text(encoding="utf-8")
            gitignore_path.write_text(existing + gitignore_additions, encoding="utf-8")
        else:
            gitignore_path.write_text(gitignore_additions.strip(), encoding="utf-8")

    def delete_project(self, client_code: str) -> bool:
        """Delete a client project directory."""
        import shutil
        client_path = self.get_client_path(client_code)
        if client_path.exists():
            shutil.rmtree(client_path)
            return True
        return False


# Singleton instance
_service: ProjectService | None = None


def get_project_service() -> ProjectService:
    """Get the project service singleton."""
    global _service
    if _service is None:
        _service = ProjectService()
    return _service
