"""Task execution service.

This module handles:
- Starting migration tasks in background
- Tracking execution progress
- Capturing logs and output
- Managing running processes
"""

import asyncio
import json
import os
import re
import signal
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Callable
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from ..config import get_settings
from ..db.models import Execution, Client
from .config_service import get_config_service


settings = get_settings()


@dataclass
class ExecutionState:
    """Track state of a running execution."""
    execution_id: int
    process: Optional[subprocess.Popen] = None
    log_lines: list = field(default_factory=list)
    is_cancelled: bool = False


# Store running executions
_running_executions: dict[int, ExecutionState] = {}


class ExecutionService:
    """Service for executing migration tasks."""

    def __init__(self, client_path: Path, db: Session):
        """Initialize with client path and database session."""
        self.client_path = client_path
        self.db = db
        self.config_service = get_config_service(client_path)

    def get_available_tasks(self) -> list[dict]:
        """Get list of tasks that can be executed from migration_config.json."""
        config_path = self.client_path / "mapping_files" / "migration_config.json"
        if not config_path.exists():
            return []

        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
            tasks = config.get("migrationTasks", [])
            return [
                {
                    "name": task.get("name"),
                    "type": task.get("migrationTaskType"),
                    "files": task.get("files", []),
                }
                for task in tasks
            ]
        except Exception:
            return []

    def create_execution(
        self,
        client_code: str,
        task_name: str,
        task_type: str,
        iteration: str,
    ) -> Execution:
        """Create a new execution record."""
        execution = Execution(
            client_code=client_code,
            task_name=task_name,
            task_type=task_type,
            iteration=iteration,
            status="pending",
        )
        self.db.add(execution)
        self.db.commit()
        self.db.refresh(execution)
        return execution

    def start_execution(
        self,
        execution: Execution,
        folio_password: str,
        on_progress: Optional[Callable] = None,
    ) -> bool:
        """Start task execution in background thread."""
        # Get paths
        config_path = self.client_path / "mapping_files" / "migration_config.json"
        base_folder = str(self.client_path)

        # Prepare log file path
        log_dir = self.client_path / "iterations" / execution.iteration / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = log_dir / f"{execution.task_name}_{timestamp}.log"

        # Update execution record
        execution.status = "running"
        execution.started_at = datetime.now(timezone.utc)
        execution.log_file = str(log_file.relative_to(self.client_path))
        self.db.commit()

        # Create execution state
        state = ExecutionState(execution_id=execution.id)
        _running_executions[execution.id] = state

        # Start in background thread
        thread = threading.Thread(
            target=self._run_task,
            args=(execution.id, config_path, execution.task_name, base_folder,
                  folio_password, log_file, on_progress),
            daemon=True,
        )
        thread.start()

        return True

    def _run_task(
        self,
        execution_id: int,
        config_path: Path,
        task_name: str,
        base_folder: str,
        folio_password: str,
        log_file: Path,
        on_progress: Optional[Callable],
    ):
        """Run the migration task (called in background thread)."""
        from ..db.database import SessionLocal

        # Create new DB session for this thread
        db = SessionLocal()
        state = _running_executions.get(execution_id)

        try:
            execution = db.query(Execution).filter(Execution.id == execution_id).first()
            if not execution:
                return

            # Build command
            # Use the folio-migration-tools command
            cmd = [
                sys.executable, "-m", "folio_migration_tools",
                str(config_path),
                task_name,
                "--base_folder_path", base_folder,
                "--folio_password", folio_password,
            ]

            # Start process
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=base_folder,
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
            )

            if state:
                state.process = process
            execution.pid = process.pid
            db.commit()

            # Open log file for writing
            with open(log_file, "w", encoding="utf-8") as f:
                # Read output line by line
                for line in iter(process.stdout.readline, ""):
                    if state and state.is_cancelled:
                        break

                    # Write to log file
                    f.write(line)
                    f.flush()

                    # Store in state
                    if state:
                        state.log_lines.append(line.rstrip())
                        # Keep only last 1000 lines in memory
                        if len(state.log_lines) > 1000:
                            state.log_lines = state.log_lines[-1000:]

                    # Parse progress from output
                    progress_info = self._parse_progress(line)
                    if progress_info and execution:
                        if progress_info.get("total"):
                            execution.total_records = progress_info["total"]
                        if progress_info.get("processed"):
                            execution.processed_records = progress_info["processed"]
                        if progress_info.get("success"):
                            execution.success_count = progress_info["success"]
                        if progress_info.get("errors"):
                            execution.error_count = progress_info["errors"]
                        if execution.total_records > 0:
                            execution.progress_percent = (
                                execution.processed_records / execution.total_records * 100
                            )
                        db.commit()

                        if on_progress:
                            on_progress(execution)

            # Wait for process to complete
            return_code = process.wait()

            # Update final status
            execution = db.query(Execution).filter(Execution.id == execution_id).first()
            if execution:
                execution.completed_at = datetime.now(timezone.utc)
                if execution.started_at:
                    duration = (execution.completed_at - execution.started_at).total_seconds()
                    execution.duration_seconds = duration

                if state and state.is_cancelled:
                    execution.status = "cancelled"
                elif return_code == 0:
                    execution.status = "completed"
                    # Try to read result summary
                    execution.result_summary = self._get_result_summary(
                        base_folder, execution.iteration, task_name
                    )
                else:
                    execution.status = "failed"
                    execution.error_message = f"Process exited with code {return_code}"

                db.commit()

        except Exception as e:
            # Update execution with error
            execution = db.query(Execution).filter(Execution.id == execution_id).first()
            if execution:
                execution.status = "failed"
                execution.error_message = str(e)
                execution.completed_at = datetime.now(timezone.utc)
                db.commit()
        finally:
            # Cleanup
            if execution_id in _running_executions:
                del _running_executions[execution_id]
            db.close()

    def _parse_progress(self, line: str) -> Optional[dict]:
        """Parse progress information from log line."""
        # Common patterns in folio_migration_tools output
        patterns = [
            # "Processed 100 of 1000 records"
            r"Processed (\d+) of (\d+)",
            # "Records: 100/1000"
            r"Records:\s*(\d+)/(\d+)",
            # "Progress: 50%"
            r"Progress:\s*(\d+)%",
            # "Transformed 500 records"
            r"Transformed (\d+) records",
            # "Created 100 Instance records"
            r"Created (\d+) \w+ records",
            # "Failed: 5"
            r"Failed:\s*(\d+)",
            # "Errors: 10"
            r"Errors:\s*(\d+)",
        ]

        result = {}

        # Check for processed/total
        match = re.search(r"Processed (\d+) of (\d+)", line, re.IGNORECASE)
        if match:
            result["processed"] = int(match.group(1))
            result["total"] = int(match.group(2))

        # Check for records ratio
        match = re.search(r"(\d+)/(\d+)\s*records", line, re.IGNORECASE)
        if match:
            result["processed"] = int(match.group(1))
            result["total"] = int(match.group(2))

        # Check for created count
        match = re.search(r"Created (\d+)", line, re.IGNORECASE)
        if match:
            result["success"] = int(match.group(1))

        # Check for error count
        match = re.search(r"(?:Failed|Errors?):\s*(\d+)", line, re.IGNORECASE)
        if match:
            result["errors"] = int(match.group(1))

        return result if result else None

    def _get_result_summary(self, base_folder: str, iteration: str, task_name: str) -> Optional[str]:
        """Read the migration report to get result summary."""
        # Look for migration_report_raw.json in results folder
        results_path = Path(base_folder) / "iterations" / iteration / "results"

        # Find the task folder (could be under different object type folders)
        for obj_folder in results_path.iterdir() if results_path.exists() else []:
            task_folder = obj_folder / task_name
            if task_folder.exists():
                report_file = task_folder / "migration_report_raw.json"
                if report_file.exists():
                    try:
                        return report_file.read_text(encoding="utf-8")
                    except Exception:
                        pass
        return None

    def cancel_execution(self, execution_id: int) -> bool:
        """Cancel a running execution."""
        state = _running_executions.get(execution_id)
        if not state:
            return False

        state.is_cancelled = True
        if state.process:
            try:
                # Try graceful termination first
                state.process.terminate()
                # Give it a moment to cleanup
                try:
                    state.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    # Force kill
                    state.process.kill()
                return True
            except Exception:
                return False
        return False

    def get_execution_logs(self, execution_id: int, offset: int = 0) -> list[str]:
        """Get logs for a running execution."""
        state = _running_executions.get(execution_id)
        if state:
            return state.log_lines[offset:]
        return []

    def is_running(self, execution_id: int) -> bool:
        """Check if an execution is currently running."""
        return execution_id in _running_executions


def get_execution_service(client_path: Path, db: Session) -> ExecutionService:
    """Get execution service instance."""
    return ExecutionService(client_path, db)
