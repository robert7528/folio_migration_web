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
from datetime import datetime
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
                    "files": self._extract_input_files(task),
                }
                for task in tasks
            ]
        except Exception:
            return []

    def _extract_input_files(self, task: dict) -> list[dict]:
        """Extract input files from task config, handling different field names."""
        files = []

        # Standard files array (BibsTransformer, BatchPoster, ItemsTransformer, etc.)
        if "files" in task:
            files.extend(task["files"])

        # UserTransformer uses userFile
        if "userFile" in task:
            files.append(task["userFile"])

        # LoansMigrator uses openLoansFiles
        if "openLoansFiles" in task:
            files.extend(task["openLoansFiles"])

        # RequestsMigrator uses openRequestsFile
        if "openRequestsFile" in task:
            files.append(task["openRequestsFile"])

        # CoursesMigrator uses coursesFile
        if "coursesFile" in task:
            files.append(task["coursesFile"])

        # ReservesMigrator uses courseReserveFilePath
        if "courseReserveFilePath" in task:
            files.append(task["courseReserveFilePath"])

        return files

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
        execution.started_at = datetime.now()
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

            # Find the project's Python executable
            # Each project has its own .venv with folio_migration_tools installed
            project_python = Path(base_folder) / ".venv" / "bin" / "python"
            if not project_python.exists():
                # Try Windows path
                project_python = Path(base_folder) / ".venv" / "Scripts" / "python.exe"

            if not project_python.exists():
                raise FileNotFoundError(
                    f"Project virtual environment not found at {base_folder}/.venv. "
                    "Please ensure folio_migration_tools is installed in the project."
                )

            # Build command using project's Python
            cmd = [
                str(project_python), "-m", "folio_migration_tools",
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
                        # Increment error count for each ERROR/CRITICAL log line
                        if progress_info.get("error_increment"):
                            execution.error_count = (execution.error_count or 0) + progress_info["error_increment"]
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
                execution.completed_at = datetime.now()
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
                    # Try to get statistics from report file
                    stats = self._get_stats_from_report(
                        base_folder, execution.iteration, task_name
                    )
                    if stats:
                        if stats.get("total"):
                            execution.total_records = stats["total"]
                        if stats.get("processed"):
                            execution.processed_records = stats["processed"]
                        if stats.get("success"):
                            execution.success_count = stats["success"]
                        if stats.get("errors"):
                            execution.error_count = stats["errors"]
                        if stats.get("merged"):
                            execution.merged_count = stats["merged"]
                        if execution.total_records > 0:
                            execution.progress_percent = (
                                execution.processed_records / execution.total_records * 100
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
                execution.completed_at = datetime.now()
                db.commit()
        finally:
            # Cleanup
            if execution_id in _running_executions:
                del _running_executions[execution_id]
            db.close()

    def _parse_progress(self, line: str) -> Optional[dict]:
        """Parse progress information from log line.

        folio_migration_tools log format:
        timestamp    INFO    message    task_name

        Key patterns to match:
        - "Done reading 14 records from file"
        - "14 records processed"
        - "Processed 100 of 1000 records"
        - "Posted 50 records"
        - "Posting successful! Total rows: 128 Total failed: 0 created: 0 updated: 128"
        - "Done posting 128 records."
        """
        result = {}

        # folio_migration_tools: "Done reading 14 records from file"
        match = re.search(r"Done reading (\d+) records from file", line, re.IGNORECASE)
        if match:
            result["total"] = int(match.group(1))

        # folio_migration_tools: "14 records processed"
        match = re.search(r"(\d+) records processed", line, re.IGNORECASE)
        if match:
            count = int(match.group(1))
            result["processed"] = count
            result["success"] = count

        # folio_migration_tools: "Saving map of 14 old and new IDs"
        match = re.search(r"Saving map of (\d+) old and new IDs", line, re.IGNORECASE)
        if match:
            result["success"] = int(match.group(1))

        # BatchPoster: "Posting successful! Total rows: 128 Total failed: 0 created: 0 updated: 128"
        match = re.search(r"Posting successful!.*Total rows:\s*(\d+).*Total failed:\s*(\d+)", line, re.IGNORECASE)
        if match:
            total_rows = int(match.group(1))
            total_failed = int(match.group(2))
            result["total"] = total_rows
            result["processed"] = total_rows
            result["success"] = total_rows - total_failed
            result["errors"] = total_failed

        # BatchPoster: "Done posting 128 records."
        match = re.search(r"Done posting (\d+) records", line, re.IGNORECASE)
        if match:
            count = int(match.group(1))
            result["total"] = count
            result["processed"] = count
            result["success"] = count

        # BatchPoster: "Posted 100 records" or "Posted 100 Instance"
        match = re.search(r"Posted (\d+)", line, re.IGNORECASE)
        if match:
            result["success"] = int(match.group(1))
            result["processed"] = int(match.group(1))

        # Generic: "Processed 100 of 1000 records"
        match = re.search(r"Processed (\d+) of (\d+)", line, re.IGNORECASE)
        if match:
            result["processed"] = int(match.group(1))
            result["total"] = int(match.group(2))

        # Generic: "Records: 100/1000" or "100/1000 records"
        match = re.search(r"(\d+)/(\d+)\s*records", line, re.IGNORECASE)
        if match:
            result["processed"] = int(match.group(1))
            result["total"] = int(match.group(2))

        # Generic: "Created 100" or "Transformed 100"
        match = re.search(r"(?:Created|Transformed) (\d+)", line, re.IGNORECASE)
        if match:
            result["success"] = int(match.group(1))

        # Error counts: "Failed: 5" or "Errors: 10" or "5 failed"
        match = re.search(r"(?:Failed|Errors?):\s*(\d+)", line, re.IGNORECASE)
        if match:
            result["errors"] = int(match.group(1))
        match = re.search(r"(\d+)\s+failed", line, re.IGNORECASE)
        if match:
            result["errors"] = int(match.group(1))

        # Detect ERROR level log lines (folio_migration_tools format)
        # Format: "timestamp    ERROR    message    task_name"
        if re.search(r"\tERROR\t|\sERROR\s", line):
            result["error_increment"] = 1

        # Detect CRITICAL level log lines
        if re.search(r"\tCRITICAL\t|\sCRITICAL\s", line):
            result["error_increment"] = 1

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

    def _get_stats_from_report(self, base_folder: str, iteration: str, task_name: str) -> Optional[dict]:
        """Extract statistics from the migration report markdown file.

        folio_migration_tools report format:
        Measure | Count
        --- | ---:
        Holdings Records Written to disk | 65
        Number of Legacy items in file | 73
        FAILED Records failed due to an error | 0
        """
        reports_path = Path(base_folder) / "iterations" / iteration / "reports"
        report_file = reports_path / f"report_{task_name}.md"

        if not report_file.exists():
            return None

        try:
            content = report_file.read_text(encoding="utf-8")
            result = {}

            # Parse folio_migration_tools report format
            # Pattern: "Measure Name | Count" where Measure is in first column

            # Total/input records patterns
            total_patterns = [
                r"Number of (?:Legacy )?(?:items|records) in file\s*\|\s*(\d+)",
                r"Number of rows in \S+\s*\|\s*(\d+)",
                r"Total records\s*\|\s*(\d+)",
                r"Source data file contains (\d+) rows",
            ]
            for pattern in total_patterns:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    result["total"] = int(match.group(1))
                    break

            # Success/written records patterns
            success_patterns = [
                r"(?:Holdings|Users|Items|Instances) Records Written to disk\s*\|\s*(\d+)",
                r"Unique (?:Holdings|Items) created from Items\s*\|\s*(\d+)",
                r"Records matched to Instances\s*\|\s*(\d+)",
                r"(?:Written|Created|Transformed)\s*\|\s*(\d+)",
                r"Saving map of (\d+) old and new IDs",
            ]
            for pattern in success_patterns:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    result["success"] = int(match.group(1))
                    break

            # Error/failed records patterns
            error_patterns = [
                r"FAILED Records failed due to an error\s*\|\s*(\d+)",
                r"Records not matched to Instances\s*\|\s*(\d+)",
                r"Failed\s*\|\s*(\d+)",
                r"Errors\s*\|\s*(\d+)",
            ]
            for pattern in error_patterns:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    error_count = int(match.group(1))
                    if error_count > 0:
                        result["errors"] = error_count
                    break

            # Merged/duplicate records patterns (not errors, just merged)
            merged_patterns = [
                r"Holdings already created from Item\s*\|\s*(\d+)",
                r"Items already created\s*\|\s*(\d+)",
                r"(?:Merged|Duplicate)\s*\|\s*(\d+)",
            ]
            for pattern in merged_patterns:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    merged_count = int(match.group(1))
                    if merged_count > 0:
                        result["merged"] = merged_count
                    break

            # Processed records (usually same as success + errors or total)
            if "success" in result:
                result["processed"] = result.get("success", 0) + result.get("errors", 0)
            elif "total" in result:
                result["processed"] = result["total"]

            # If no stats from report, try counting lines in output JSON file
            if not result:
                results_path = Path(base_folder) / "iterations" / iteration / "results"
                # Try different output file patterns
                for pattern in [f"folio_*_{task_name}.json", f"folio_{task_name}.json"]:
                    for result_file in results_path.glob(pattern):
                        try:
                            with open(result_file, "r", encoding="utf-8") as f:
                                count = sum(1 for line in f if line.strip())
                            result["total"] = count
                            result["processed"] = count
                            result["success"] = count
                            break
                        except Exception:
                            pass
                    if result:
                        break

            return result if result else None
        except Exception:
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
