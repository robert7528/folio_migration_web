"""FOLIO data validation service.

This module handles:
- Connecting to FOLIO API for data verification
- Querying records from FOLIO platform
- Comparing transformation results with FOLIO data
- Generating validation reports
"""

import json
import httpx
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field, asdict
from enum import Enum

from sqlalchemy.orm import Session

from ..config import get_settings
from ..db.models import Execution, Client


settings = get_settings()


class RecordType(str, Enum):
    """Supported record types for validation."""
    INSTANCES = "instances"
    HOLDINGS = "holdings"
    ITEMS = "items"
    USERS = "users"


@dataclass
class ValidationResult:
    """Result of a single record validation."""
    legacy_id: str
    folio_id: Optional[str] = None
    hrid: Optional[str] = None
    status: str = "pending"  # found, not_found, mismatch, error
    local_data: Optional[Dict] = None
    folio_data: Optional[Dict] = None
    differences: List[Dict] = field(default_factory=list)
    error_message: Optional[str] = None


@dataclass
class ValidationSummary:
    """Summary of validation results."""
    record_type: str
    total_local_records: int = 0
    total_found_in_folio: int = 0
    total_not_found: int = 0
    total_mismatches: int = 0
    total_errors: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    results: List[ValidationResult] = field(default_factory=list)

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "record_type": self.record_type,
            "total_local_records": self.total_local_records,
            "total_found_in_folio": self.total_found_in_folio,
            "total_not_found": self.total_not_found,
            "total_mismatches": self.total_mismatches,
            "total_errors": self.total_errors,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "results": [asdict(r) for r in self.results],
        }


class FolioApiClient:
    """Client for FOLIO API interactions."""

    def __init__(self, folio_url: str, tenant_id: str, token: str):
        """Initialize with FOLIO connection details."""
        self.folio_url = folio_url.rstrip("/")
        self.tenant_id = tenant_id
        self.token = token
        self.headers = {
            "x-okapi-tenant": tenant_id,
            "x-okapi-token": token,
            "Content-Type": "application/json",
        }

    @classmethod
    async def create(cls, folio_url: str, tenant_id: str, username: str, password: str) -> "FolioApiClient":
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

            # Get token from header or body
            token = response.headers.get("x-okapi-token")
            if not token:
                body = response.json()
                token = body.get("okapiToken") or body.get("accessToken")

            if not token:
                raise Exception("Failed to obtain authentication token")

            return cls(folio_url, tenant_id, token)

    async def query_instances(
        self,
        query: str,
        limit: int = 100,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Query instances from FOLIO."""
        return await self._query_records(
            "/instance-storage/instances",
            query,
            limit,
            offset,
            "instances",
        )

    async def query_holdings(
        self,
        query: str,
        limit: int = 100,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Query holdings from FOLIO."""
        return await self._query_records(
            "/holdings-storage/holdings",
            query,
            limit,
            offset,
            "holdingsRecords",
        )

    async def query_items(
        self,
        query: str,
        limit: int = 100,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Query items from FOLIO."""
        return await self._query_records(
            "/item-storage/items",
            query,
            limit,
            offset,
            "items",
        )

    async def query_users(
        self,
        query: str,
        limit: int = 100,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Query users from FOLIO."""
        return await self._query_records(
            "/users",
            query,
            limit,
            offset,
            "users",
        )

    async def get_record_count(self, record_type: RecordType) -> int:
        """Get total count of records in FOLIO."""
        endpoint_map = {
            RecordType.INSTANCES: "/instance-storage/instances",
            RecordType.HOLDINGS: "/holdings-storage/holdings",
            RecordType.ITEMS: "/item-storage/items",
            RecordType.USERS: "/users",
        }
        endpoint = endpoint_map.get(record_type)
        if not endpoint:
            return 0

        async with httpx.AsyncClient(timeout=30.0) as client:
            url = f"{self.folio_url}{endpoint}?limit=0"
            response = await client.get(url, headers=self.headers)
            if response.status_code == 200:
                data = response.json()
                return data.get("totalRecords", 0)
            return 0

    async def _query_records(
        self,
        endpoint: str,
        query: str,
        limit: int,
        offset: int,
        records_key: str,
    ) -> Dict[str, Any]:
        """Generic record query method."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            url = f"{self.folio_url}{endpoint}"
            params = {"query": query, "limit": limit, "offset": offset}

            response = await client.get(url, headers=self.headers, params=params)

            if response.status_code != 200:
                raise Exception(f"FOLIO query failed: {response.status_code} - {response.text}")

            data = response.json()
            return {
                "records": data.get(records_key, []),
                "totalRecords": data.get("totalRecords", 0),
            }

    async def get_instance_by_hrid(self, hrid: str) -> Optional[Dict]:
        """Get instance by HRID."""
        result = await self.query_instances(f'hrid=="{hrid}"', limit=1)
        records = result.get("records", [])
        return records[0] if records else None

    async def get_instance_by_id(self, instance_id: str) -> Optional[Dict]:
        """Get instance by UUID."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            url = f"{self.folio_url}/instance-storage/instances/{instance_id}"
            response = await client.get(url, headers=self.headers)
            if response.status_code == 200:
                return response.json()
            return None

    async def get_holding_by_id(self, holding_id: str) -> Optional[Dict]:
        """Get holding by UUID."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            url = f"{self.folio_url}/holdings-storage/holdings/{holding_id}"
            response = await client.get(url, headers=self.headers)
            if response.status_code == 200:
                return response.json()
            return None

    async def get_item_by_id(self, item_id: str) -> Optional[Dict]:
        """Get item by UUID."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            url = f"{self.folio_url}/item-storage/items/{item_id}"
            response = await client.get(url, headers=self.headers)
            if response.status_code == 200:
                return response.json()
            return None

    async def get_holding_by_hrid(self, hrid: str) -> Optional[Dict]:
        """Get holding by HRID."""
        result = await self.query_holdings(f'hrid=="{hrid}"', limit=1)
        records = result.get("records", [])
        return records[0] if records else None

    async def get_item_by_hrid(self, hrid: str) -> Optional[Dict]:
        """Get item by HRID."""
        result = await self.query_items(f'hrid=="{hrid}"', limit=1)
        records = result.get("records", [])
        return records[0] if records else None

    async def get_item_by_barcode(self, barcode: str) -> Optional[Dict]:
        """Get item by barcode."""
        result = await self.query_items(f'barcode=="{barcode}"', limit=1)
        records = result.get("records", [])
        return records[0] if records else None

    async def get_user_by_external_id(self, external_id: str) -> Optional[Dict]:
        """Get user by external system ID."""
        result = await self.query_users(f'externalSystemId=="{external_id}"', limit=1)
        records = result.get("records", [])
        return records[0] if records else None

    async def get_user_by_barcode(self, barcode: str) -> Optional[Dict]:
        """Get user by barcode."""
        result = await self.query_users(f'barcode=="{barcode}"', limit=1)
        records = result.get("records", [])
        return records[0] if records else None


class ValidationService:
    """Service for validating migration data against FOLIO."""

    def __init__(self, client_path: Path, db: Session):
        """Initialize with client path and database session."""
        self.client_path = client_path
        self.db = db

    async def validate_execution(
        self,
        execution: Execution,
        folio_client: FolioApiClient,
        sample_size: Optional[int] = None,
    ) -> ValidationSummary:
        """Validate an execution's output against FOLIO data."""
        # Determine record type from task type
        record_type = self._get_record_type(execution.task_type, execution.task_name)
        if not record_type:
            raise ValueError(f"Unsupported task type for validation: {execution.task_type} ({execution.task_name})")

        # Find output file
        output_file = self._find_output_file(execution)
        if not output_file:
            raise FileNotFoundError(f"Output file not found for execution {execution.id}")

        # Load local records
        local_records = self._load_local_records(output_file, record_type)

        # Apply sample size if specified
        if sample_size and sample_size < len(local_records):
            import random
            local_records = random.sample(local_records, sample_size)

        # Create summary
        summary = ValidationSummary(
            record_type=record_type.value,
            total_local_records=len(local_records),
            started_at=datetime.now(),
        )

        # Validate each record
        for record in local_records:
            result = await self._validate_record(record, record_type, folio_client)
            summary.results.append(result)

            # Update counts
            if result.status == "found":
                summary.total_found_in_folio += 1
            elif result.status == "not_found":
                summary.total_not_found += 1
            elif result.status == "mismatch":
                summary.total_mismatches += 1
            elif result.status == "error":
                summary.total_errors += 1

        summary.completed_at = datetime.now()
        if summary.started_at:
            summary.duration_seconds = (summary.completed_at - summary.started_at).total_seconds()

        return summary

    def _get_record_type(self, task_type: str, task_name: str = "") -> Optional[RecordType]:
        """Map task type to record type."""
        mapping = {
            "BibsTransformer": RecordType.INSTANCES,
            "BibsAndItemsTransformer": RecordType.INSTANCES,
            "HoldingsTransformer": RecordType.HOLDINGS,
            "HoldingsCsvTransformer": RecordType.HOLDINGS,
            "HoldingsHridMerger": RecordType.HOLDINGS,
            "ItemsTransformer": RecordType.ITEMS,
            "ItemsCsvTransformer": RecordType.ITEMS,
            "UserTransformer": RecordType.USERS,
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

    def _load_local_records(self, file_path: Path, record_type: RecordType) -> List[Dict]:
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

    async def _validate_record(
        self,
        local_record: Dict,
        record_type: RecordType,
        folio_client: FolioApiClient,
    ) -> ValidationResult:
        """Validate a single record against FOLIO."""
        # Extract identifiers
        legacy_id = self._extract_legacy_id(local_record, record_type)
        folio_id = local_record.get("id")
        hrid = local_record.get("hrid")

        result = ValidationResult(
            legacy_id=legacy_id or folio_id or "unknown",
            folio_id=folio_id,
            hrid=hrid,
            local_data=local_record,
        )

        try:
            # Query FOLIO for the record
            folio_record = await self._fetch_folio_record(
                local_record, record_type, folio_client
            )

            if folio_record:
                result.folio_data = folio_record
                result.folio_id = folio_record.get("id")
                # Update HRID from FOLIO record (actual HRID on platform)
                result.hrid = folio_record.get("hrid")

                # Compare records
                differences = self._compare_records(local_record, folio_record, record_type)
                if differences:
                    result.status = "mismatch"
                    result.differences = differences
                else:
                    result.status = "found"
            else:
                result.status = "not_found"

        except Exception as e:
            result.status = "error"
            result.error_message = str(e)

        return result

    def _extract_legacy_id(self, record: Dict, record_type: RecordType) -> Optional[str]:
        """Extract legacy ID from record."""
        # For instances/holdings/items, HRID is typically the legacy ID
        if record_type in (RecordType.INSTANCES, RecordType.HOLDINGS, RecordType.ITEMS):
            hrid = record.get("hrid")
            if hrid:
                return hrid

        # Check common legacy ID locations
        if "legacyIdentifier" in record:
            return record["legacyIdentifier"]

        # Check identifiers array for instances
        if record_type == RecordType.INSTANCES:
            for identifier in record.get("identifiers", []):
                if "legacy" in identifier.get("identifierTypeId", "").lower():
                    return identifier.get("value")

        # Check externalSystemId for users
        if record_type == RecordType.USERS:
            return record.get("externalSystemId") or record.get("barcode")

        return None

    async def _fetch_folio_record(
        self,
        local_record: Dict,
        record_type: RecordType,
        folio_client: FolioApiClient,
    ) -> Optional[Dict]:
        """Fetch corresponding record from FOLIO."""
        record_id = local_record.get("id")
        hrid = local_record.get("hrid")

        # Try by UUID first
        if record_id:
            fetch_by_id = {
                RecordType.INSTANCES: folio_client.get_instance_by_id,
                RecordType.HOLDINGS: folio_client.get_holding_by_id,
                RecordType.ITEMS: folio_client.get_item_by_id,
            }
            fetcher = fetch_by_id.get(record_type)
            if fetcher:
                result = await fetcher(record_id)
                if result:
                    return result

        # Try by HRID for instances/holdings/items
        if hrid and record_type in (RecordType.INSTANCES, RecordType.HOLDINGS, RecordType.ITEMS):
            fetch_by_hrid = {
                RecordType.INSTANCES: folio_client.get_instance_by_hrid,
                RecordType.HOLDINGS: folio_client.get_holding_by_hrid,
                RecordType.ITEMS: folio_client.get_item_by_hrid,
            }
            fetcher = fetch_by_hrid.get(record_type)
            if fetcher:
                result = await fetcher(hrid)
                if result:
                    return result

        # Try by barcode for items
        if record_type == RecordType.ITEMS:
            barcode = local_record.get("barcode")
            if barcode:
                return await folio_client.get_item_by_barcode(barcode)

        # Try by external ID / barcode for users
        if record_type == RecordType.USERS:
            external_id = local_record.get("externalSystemId")
            if external_id:
                return await folio_client.get_user_by_external_id(external_id)
            barcode = local_record.get("barcode")
            if barcode:
                return await folio_client.get_user_by_barcode(barcode)

        return None

    def _compare_records(
        self,
        local_record: Dict,
        folio_record: Dict,
        record_type: RecordType,
    ) -> List[Dict]:
        """Compare local and FOLIO records, return differences."""
        differences = []

        # Define key fields to compare for each record type
        compare_fields = self._get_compare_fields(record_type)

        for field_path in compare_fields:
            local_value = self._get_nested_value(local_record, field_path)
            folio_value = self._get_nested_value(folio_record, field_path)

            if local_value != folio_value:
                differences.append({
                    "field": field_path,
                    "local_value": local_value,
                    "folio_value": folio_value,
                })

        return differences

    def _get_compare_fields(self, record_type: RecordType) -> List[str]:
        """Get fields to compare for each record type.

        Note: hrid is excluded for instances/holdings/items because:
        - Local file contains legacy ID in hrid field
        - FOLIO auto-generates new HRID when hridHandling="default"
        - They will always be different, which is expected behavior

        Note: Reference data fields (patronGroup, materialTypeId, etc.) are excluded
        because:
        - Local file may contain legacy codes (e.g., "C1")
        - FOLIO stores resolved UUIDs (e.g., "227c762a-71a4-4aa4-...")
        - Direct comparison would always show mismatch
        - These are validated during transformation, not here
        """
        fields_map = {
            RecordType.INSTANCES: [
                "title",
                "source",
                # instanceTypeId and modeOfIssuanceId are reference data UUIDs
            ],
            RecordType.HOLDINGS: [
                "instanceId",
                "permanentLocationId",
                "callNumber",
            ],
            RecordType.ITEMS: [
                "holdingsRecordId",
                "barcode",
                # materialTypeId and permanentLoanTypeId are reference data UUIDs
            ],
            RecordType.USERS: [
                "username",
                "barcode",
                "active",
                # patronGroup excluded: local has legacy code, FOLIO has UUID
                "personal.lastName",
                "personal.firstName",
            ],
        }
        return fields_map.get(record_type, [])

    def _get_nested_value(self, obj: Dict, path: str) -> Any:
        """Get nested value from dict using dot notation."""
        keys = path.split(".")
        value = obj
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return None
        return value


@dataclass
class CountValidationResult:
    """Result of a count-based validation."""
    record_type: str
    pre_count: int
    post_count: int
    expected_count: int  # Records that were supposed to be posted
    actual_diff: int  # post_count - pre_count
    match: bool  # Whether actual_diff == expected_count
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None

    def to_dict(self) -> Dict:
        return {
            "record_type": self.record_type,
            "pre_count": self.pre_count,
            "post_count": self.post_count,
            "expected_count": self.expected_count,
            "actual_diff": self.actual_diff,
            "match": self.match,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
        }


def get_validation_service(client_path: Path, db: Session) -> ValidationService:
    """Get validation service instance."""
    return ValidationService(client_path, db)
