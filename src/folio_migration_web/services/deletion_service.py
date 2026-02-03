"""FOLIO batch deletion service.

This module handles:
- Batch deletion of records from FOLIO platform
- Deletion order management (Items -> Holdings -> Instances)
- Progress tracking and error handling
"""

import json
import httpx
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from enum import Enum

from sqlalchemy.orm import Session

from ..config import get_settings
from ..db.models import Execution, Client, Deletion
from .validation_service import FolioApiClient, RecordType


settings = get_settings()


@dataclass
class DeletionResult:
    """Result of a single record deletion."""
    record_id: str
    status: str = "pending"  # deleted, not_found, failed, skipped
    error_message: Optional[str] = None


@dataclass
class DeletionSummary:
    """Summary of batch deletion operation."""
    record_type: str
    total_records: int = 0
    deleted_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    not_found_count: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    failed_ids: List[Dict] = field(default_factory=list)

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "record_type": self.record_type,
            "total_records": self.total_records,
            "deleted_count": self.deleted_count,
            "failed_count": self.failed_count,
            "skipped_count": self.skipped_count,
            "not_found_count": self.not_found_count,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "failed_ids": self.failed_ids,
        }


class FolioDeletionClient(FolioApiClient):
    """Extended FOLIO client with deletion capabilities."""

    async def delete_instance(self, instance_id: str) -> Dict[str, Any]:
        """Delete a single instance from FOLIO."""
        return await self._delete_record(
            f"/instance-storage/instances/{instance_id}",
            instance_id
        )

    async def delete_holdings(self, holdings_id: str) -> Dict[str, Any]:
        """Delete a single holdings record from FOLIO."""
        return await self._delete_record(
            f"/holdings-storage/holdings/{holdings_id}",
            holdings_id
        )

    async def delete_item(self, item_id: str) -> Dict[str, Any]:
        """Delete a single item from FOLIO."""
        return await self._delete_record(
            f"/item-storage/items/{item_id}",
            item_id
        )

    async def delete_user(self, user_id: str) -> Dict[str, Any]:
        """Delete a single user from FOLIO."""
        # First delete the user's request preference (if exists)
        await self._delete_user_request_preference(user_id)
        # Then delete the user
        return await self._delete_record(
            f"/users/{user_id}",
            user_id
        )

    async def _delete_user_request_preference(self, user_id: str) -> Dict[str, Any]:
        """Delete request preference for a user (if exists).

        Returns dict with status: 'deleted', 'not_found', or 'failed'
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Query for the user's request preference
                # Note: FOLIO CQL for UUIDs should not have quotes around the value
                url = f"{self.folio_url}/request-preference-storage/request-preference"
                params = {"query": f"userId=={user_id}"}
                response = await client.get(url, headers=self.headers, params=params)

                if response.status_code != 200:
                    return {"status": "failed", "error": f"Query failed: {response.status_code}"}

                data = response.json()
                prefs = data.get("requestPreferences", [])

                if not prefs:
                    return {"status": "not_found", "user_id": user_id}

                deleted_count = 0
                for pref in prefs:
                    pref_id = pref.get("id")
                    if pref_id:
                        # Delete the request preference
                        delete_url = f"{self.folio_url}/request-preference-storage/request-preference/{pref_id}"
                        del_response = await client.delete(delete_url, headers=self.headers)
                        if del_response.status_code == 204:
                            deleted_count += 1

                if deleted_count > 0:
                    return {"status": "deleted", "user_id": user_id, "count": deleted_count}
                else:
                    return {"status": "failed", "user_id": user_id, "error": "Delete requests failed"}

        except Exception as e:
            return {"status": "failed", "user_id": user_id, "error": str(e)}

    async def _delete_record(self, endpoint: str, record_id: str) -> Dict[str, Any]:
        """Generic record deletion method."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            url = f"{self.folio_url}{endpoint}"
            response = await client.delete(url, headers=self.headers)

            if response.status_code == 204:
                return {"status": "deleted", "id": record_id}
            elif response.status_code == 404:
                return {
                    "status": "not_found",
                    "id": record_id,
                    "error": f"HTTP 404: Record not found at {endpoint}"
                }
            else:
                error_msg = response.text
                try:
                    error_data = response.json()
                    error_msg = error_data.get("errors", [{}])[0].get("message", response.text)
                except:
                    pass
                return {
                    "status": "failed",
                    "id": record_id,
                    "error": f"HTTP {response.status_code}: {error_msg}"
                }

    async def check_holdings_for_instance(self, instance_id: str) -> List[str]:
        """Get holdings IDs associated with an instance."""
        result = await self.query_holdings(f'instanceId=="{instance_id}"', limit=1000)
        return [h["id"] for h in result.get("records", [])]

    async def check_items_for_holdings(self, holdings_id: str) -> List[str]:
        """Get item IDs associated with a holdings record."""
        result = await self.query_items(f'holdingsRecordId=="{holdings_id}"', limit=1000)
        return [i["id"] for i in result.get("records", [])]

    @classmethod
    async def create(cls, folio_url: str, tenant_id: str, username: str, password: str) -> "FolioDeletionClient":
        """Create client by authenticating with FOLIO."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            auth_url = f"{folio_url.rstrip('/')}/authn/login"
            headers = {
                "Content-Type": "application/json",
                "x-okapi-tenant": tenant_id,
            }
            payload = {"username": username, "password": password}

            response = await client.post(auth_url, json=payload, headers=headers)

            if response.status_code not in (200, 201):
                raise Exception(f"FOLIO authentication failed: {response.status_code}")

            token = response.headers.get("x-okapi-token")
            if not token:
                body = response.json()
                token = body.get("okapiToken") or body.get("accessToken")

            if not token:
                raise Exception("Failed to obtain authentication token")

            return cls(folio_url, tenant_id, token)


class DeletionService:
    """Service for batch deleting migration data from FOLIO."""

    def __init__(self, client_path: Path, db: Session):
        """Initialize with client path and database session."""
        self.client_path = client_path
        self.db = db

    async def delete_execution_records(
        self,
        execution: Execution,
        folio_client: FolioDeletionClient,
        deletion_record: Deletion,
        cascade: bool = True,
    ) -> DeletionSummary:
        """Delete all records from an execution.

        Args:
            execution: The execution record
            folio_client: FOLIO API client with delete capabilities
            deletion_record: Database record to track progress
            cascade: If True, delete dependent records (holdings, items) first
        """
        # Determine record type from task type
        record_type = self._get_record_type(execution.task_type, execution.task_name)
        if not record_type:
            raise ValueError(f"Unsupported task type for deletion: {execution.task_type} ({execution.task_name})")

        # Find output file
        output_file = self._find_output_file(execution)
        if not output_file:
            raise FileNotFoundError(f"Output file not found for execution {execution.id}")

        # Load records to get UUIDs
        records = self._load_records(output_file, record_type)
        record_ids = [r.get("id") for r in records if r.get("id")]

        # Create summary
        summary = DeletionSummary(
            record_type=record_type.value,
            total_records=len(record_ids),
            started_at=datetime.now(),
        )

        # Update deletion record
        deletion_record.total_records = len(record_ids)
        deletion_record.status = "running"
        deletion_record.started_at = summary.started_at
        self.db.commit()

        # Delete records
        for i, record_id in enumerate(record_ids):
            try:
                result = await self._delete_single_record(
                    record_id, record_type, folio_client, cascade
                )

                if result["status"] == "deleted":
                    summary.deleted_count += 1
                elif result["status"] == "not_found":
                    summary.not_found_count += 1
                    summary.skipped_count += 1
                    # Track not_found records for debugging
                    summary.failed_ids.append({
                        "id": record_id,
                        "error": result.get("error", "Not found in FOLIO")
                    })
                elif result["status"] == "skipped":
                    summary.skipped_count += 1
                else:
                    summary.failed_count += 1
                    summary.failed_ids.append({
                        "id": record_id,
                        "error": result.get("error", "Unknown error")
                    })

            except Exception as e:
                summary.failed_count += 1
                summary.failed_ids.append({
                    "id": record_id,
                    "error": str(e)
                })

            # Update progress
            progress = ((i + 1) / len(record_ids)) * 100 if record_ids else 100
            deletion_record.deleted_count = summary.deleted_count
            deletion_record.failed_count = summary.failed_count
            deletion_record.skipped_count = summary.skipped_count
            deletion_record.progress_percent = progress
            self.db.commit()

        # Finalize
        summary.completed_at = datetime.now()
        if summary.started_at:
            summary.duration_seconds = (summary.completed_at - summary.started_at).total_seconds()

        deletion_record.status = "completed"
        deletion_record.completed_at = summary.completed_at
        deletion_record.duration_seconds = summary.duration_seconds
        deletion_record.failed_ids_json = json.dumps(summary.failed_ids) if summary.failed_ids else None
        self.db.commit()

        return summary

    async def _delete_single_record(
        self,
        record_id: str,
        record_type: RecordType,
        folio_client: FolioDeletionClient,
        cascade: bool,
    ) -> Dict[str, Any]:
        """Delete a single record with optional cascade."""

        if record_type == RecordType.INSTANCES:
            if cascade:
                # First delete all items under all holdings
                holdings_ids = await folio_client.check_holdings_for_instance(record_id)
                for holdings_id in holdings_ids:
                    item_ids = await folio_client.check_items_for_holdings(holdings_id)
                    for item_id in item_ids:
                        await folio_client.delete_item(item_id)
                    await folio_client.delete_holdings(holdings_id)

            return await folio_client.delete_instance(record_id)

        elif record_type == RecordType.HOLDINGS:
            if cascade:
                # First delete all items under this holdings
                item_ids = await folio_client.check_items_for_holdings(record_id)
                for item_id in item_ids:
                    await folio_client.delete_item(item_id)

            return await folio_client.delete_holdings(record_id)

        elif record_type == RecordType.ITEMS:
            return await folio_client.delete_item(record_id)

        elif record_type == RecordType.USERS:
            return await folio_client.delete_user(record_id)

        return {"status": "skipped", "error": f"Unsupported record type: {record_type}"}

    def _get_record_type(self, task_type: str, task_name: str = "") -> Optional[RecordType]:
        """Map task type to record type."""
        mapping = {
            "BibsTransformer": RecordType.INSTANCES,
            "HoldingsTransformer": RecordType.HOLDINGS,
            "ItemsTransformer": RecordType.ITEMS,
            "UserTransformer": RecordType.USERS,
            "BibsAndItemsTransformer": RecordType.INSTANCES,
        }

        # Direct mapping
        if task_type in mapping:
            return mapping.get(task_type)

        # For BatchPoster, determine type from task_name
        if task_type == "BatchPoster":
            task_name_lower = task_name.lower()
            if "instance" in task_name_lower:
                return RecordType.INSTANCES
            elif "holding" in task_name_lower:
                return RecordType.HOLDINGS
            elif "item" in task_name_lower:
                return RecordType.ITEMS
            elif "user" in task_name_lower:
                return RecordType.USERS

        return None

    def _find_output_file(self, execution: Execution) -> Optional[Path]:
        """Find the output JSON file for an execution.

        For Transformer tasks: looks for folio_*{task_name}.json
        For BatchPoster tasks: looks for the Transformer output file that was used as input
        """
        iteration_path = self.client_path / "iterations" / execution.iteration
        results_path = iteration_path / "results"

        if not results_path.exists():
            return None

        # For BatchPoster tasks, find the Transformer output file (the input file for posting)
        # BatchPoster doesn't create new records, it posts records from Transformer output
        if execution.task_type == "BatchPoster":
            record_type = self._get_record_type(execution.task_type, execution.task_name)
            if record_type:
                # Map record type to expected file pattern
                type_to_pattern = {
                    RecordType.INSTANCES: "folio_instances_",
                    RecordType.HOLDINGS: "folio_holdings_",
                    RecordType.ITEMS: "folio_items_",
                    RecordType.USERS: "folio_users_",
                }
                pattern = type_to_pattern.get(record_type)
                if pattern:
                    for f in results_path.rglob("*.json"):
                        if f.name.startswith(pattern) and "other" not in f.name:
                            return f

        # Look for folio_*.json files containing the task name
        for f in results_path.rglob("folio_*.json"):
            if execution.task_name in f.name:
                return f

        # Also check directly in results folder
        for f in results_path.glob("*.json"):
            if "folio" in f.name.lower() and execution.task_name in f.name:
                return f

        return None

    def _load_records(self, file_path: Path, record_type: RecordType) -> List[Dict]:
        """Load records from local JSON file."""
        content = file_path.read_text(encoding="utf-8")

        # Handle JSONL format (one JSON object per line)
        records = []
        for line in content.strip().split("\n"):
            if line.strip():
                try:
                    record = json.loads(line)
                    records.append(record)
                except json.JSONDecodeError:
                    continue

        # If not JSONL, try as single JSON array
        if not records:
            try:
                data = json.loads(content)
                if isinstance(data, list):
                    records = data
                elif isinstance(data, dict):
                    # Handle wrapped format
                    for key in ["instances", "holdingsRecords", "items", "users"]:
                        if key in data:
                            records = data[key]
                            break
            except json.JSONDecodeError:
                pass

        return records

    def preview_deletion(
        self,
        execution: Execution,
    ) -> Dict[str, Any]:
        """Preview what will be deleted without actually deleting."""
        record_type = self._get_record_type(execution.task_type, execution.task_name)
        if not record_type:
            raise ValueError(f"Unsupported task type: {execution.task_type} ({execution.task_name})")

        output_file = self._find_output_file(execution)
        if not output_file:
            raise FileNotFoundError(f"Output file not found for execution {execution.id}")

        records = self._load_records(output_file, record_type)

        return {
            "execution_id": execution.id,
            "task_name": execution.task_name,
            "task_type": execution.task_type,
            "record_type": record_type.value,
            "total_records": len(records),
            "output_file": str(output_file),
            "sample_ids": [r.get("id") for r in records[:5] if r.get("id")],
        }


def get_deletion_service(client_path: Path, db: Session) -> DeletionService:
    """Get deletion service instance."""
    return DeletionService(client_path, db)
