"""Configuration file management service.

This module handles:
- Generation of task-specific configuration files
- Generation of mapping file templates
- Merging configs into a single migration config
- Syncing libraryInformation when project info changes
- Fetching reference data from FOLIO API
"""

import json
import httpx
from pathlib import Path
from typing import Any, Optional
from datetime import date

from ..models.client import ClientCreate


# Task type definitions with their required mapping files
TASK_DEFINITIONS = {
    "bibs": {
        "name": "Bibliographic Records (Instances)",
        "transformer": "BibsTransformer",
        "poster_object_type": "Instances",
        "srs_object_type": "SRS",
        "required_mappings": [],
        "optional_mappings": [],
    },
    "authorities": {
        "name": "Authority Records",
        "transformer": "AuthorityTransformer",
        "poster_object_type": "Authorities",
        "srs_object_type": "SRS",
        "required_mappings": [],
        "optional_mappings": [],
    },
    "holdings_marc": {
        "name": "Holdings (MARC/MFHD)",
        "transformer": "HoldingsMarcTransformer",
        "poster_object_type": "Holdings",
        "srs_object_type": "SRS",
        "required_mappings": ["locations.tsv"],
        "optional_mappings": ["call_number_type_mapping.tsv"],
    },
    "holdings_csv": {
        "name": "Holdings (CSV)",
        "transformer": "HoldingsCsvTransformer",
        "poster_object_type": "Holdings",
        "required_mappings": ["locations.tsv", "holdingsrecord_mapping.json"],
        "optional_mappings": ["call_number_type_mapping.tsv"],
    },
    "items": {
        "name": "Items",
        "transformer": "ItemsTransformer",
        "poster_object_type": "Items",
        "required_mappings": [
            "locations.tsv",
            "item_mapping.json",
            "material_types.tsv",
            "loan_types.tsv",
        ],
        "optional_mappings": [
            "item_statuses.tsv",
            "call_number_type_mapping.tsv",
            "statistical_codes.tsv",
        ],
    },
    "users": {
        "name": "Users/Patrons",
        "transformer": "UserTransformer",
        "poster_object_type": "Users",
        "required_mappings": ["user_mapping.json", "user_groups.tsv"],
        "optional_mappings": ["departments.tsv"],
    },
    "loans": {
        "name": "Open Loans",
        "migrator": "LoansMigrator",
        "required_mappings": [],
        "optional_mappings": [],
    },
    "requests": {
        "name": "Open Requests",
        "migrator": "RequestsMigrator",
        "required_mappings": [],
        "optional_mappings": [],
    },
    "courses": {
        "name": "Courses",
        "migrator": "CoursesMigrator",
        "poster_object_type": "Extradata",
        "required_mappings": ["course_mapping.json", "terms_map.tsv"],
        "optional_mappings": [],
    },
    "reserves": {
        "name": "Course Reserves",
        "migrator": "ReservesMigrator",
        "required_mappings": ["reserve_locations.tsv"],
        "optional_mappings": [],
    },
    "organizations": {
        "name": "Organizations/Vendors",
        "transformer": "OrganizationTransformer",
        "required_mappings": ["organization_mapping.json"],
        "optional_mappings": [
            "organization_types.tsv",
            "address_categories.tsv",
            "email_categories.tsv",
            "phone_categories.tsv",
        ],
    },
    "orders": {
        "name": "Acquisition Orders",
        "transformer": "OrdersTransformer",
        "required_mappings": ["composite_order_mapping.json"],
        "optional_mappings": [
            "acquisition_method_map.tsv",
            "organization_code_map.tsv",
        ],
    },
    "feefines": {
        "name": "Fees/Fines",
        "transformer": "ManualFeeFinesTransformer",
        "poster_object_type": "Extradata",
        "required_mappings": [
            "manual_feefines_map.json",
            "feefine_owners.tsv",
            "feefine_types.tsv",
        ],
        "optional_mappings": ["feefines_service_points.tsv"],
    },
}


class ConfigService:
    """Service for managing migration configuration files."""

    def __init__(self, client_path: Path):
        """Initialize with client project path."""
        self.client_path = client_path
        self.mapping_files_dir = client_path / "mapping_files"
        self.tasks_dir = self.mapping_files_dir / "tasks"

    def ensure_directories(self):
        """Create necessary directories."""
        self.mapping_files_dir.mkdir(parents=True, exist_ok=True)
        self.tasks_dir.mkdir(parents=True, exist_ok=True)

    def generate_library_config(
        self,
        client_name: str,
        tenant_id: str,
        folio_url: str,
        iteration_id: str,
        folio_release: str = "sunflower",
    ) -> dict:
        """Generate the shared libraryInformation config."""
        config = {
            "libraryInformation": {
                "tenantId": tenant_id,
                "multiFieldDelimiter": "<^>",
                "okapiUrl": folio_url,
                "okapiUsername": "",
                "logLevelDebug": False,
                "libraryName": client_name,
                "folioRelease": folio_release,
                "addTimeStampToFileNames": False,
                "iterationIdentifier": iteration_id,
            }
        }

        config_path = self.mapping_files_dir / "library_config.json"
        config_path.write_text(
            json.dumps(config, indent=4, ensure_ascii=False), encoding="utf-8"
        )

        return config

    def update_library_config(
        self,
        client_name: Optional[str] = None,
        tenant_id: Optional[str] = None,
        folio_url: Optional[str] = None,
        iteration_id: Optional[str] = None,
    ):
        """Update the libraryInformation in library_config.json."""
        config_path = self.mapping_files_dir / "library_config.json"

        if not config_path.exists():
            return

        config = json.loads(config_path.read_text(encoding="utf-8"))
        lib_info = config.get("libraryInformation", {})

        if client_name:
            lib_info["libraryName"] = client_name
        if tenant_id:
            lib_info["tenantId"] = tenant_id
        if folio_url:
            lib_info["okapiUrl"] = folio_url
        if iteration_id:
            lib_info["iterationIdentifier"] = iteration_id

        config["libraryInformation"] = lib_info
        config_path.write_text(
            json.dumps(config, indent=4, ensure_ascii=False), encoding="utf-8"
        )

        # Also regenerate the combined config
        self.generate_combined_config()

    def generate_task_config(self, task_type: str) -> Optional[dict]:
        """Generate a task-specific configuration file."""
        if task_type not in TASK_DEFINITIONS:
            return None

        task_def = TASK_DEFINITIONS[task_type]
        config = {"enabled": False, "tasks": []}

        # Generate task config based on task type
        if task_type == "bibs":
            config["tasks"] = self._generate_bibs_tasks()
        elif task_type == "authorities":
            config["tasks"] = self._generate_authorities_tasks()
        elif task_type == "holdings_marc":
            config["tasks"] = self._generate_holdings_marc_tasks()
        elif task_type == "holdings_csv":
            config["tasks"] = self._generate_holdings_csv_tasks()
        elif task_type == "items":
            config["tasks"] = self._generate_items_tasks()
        elif task_type == "users":
            config["tasks"] = self._generate_users_tasks()
        elif task_type == "loans":
            config["tasks"] = self._generate_loans_tasks()
        elif task_type == "requests":
            config["tasks"] = self._generate_requests_tasks()
        elif task_type == "courses":
            config["tasks"] = self._generate_courses_tasks()
        elif task_type == "reserves":
            config["tasks"] = self._generate_reserves_tasks()
        elif task_type == "organizations":
            config["tasks"] = self._generate_organizations_tasks()
        elif task_type == "orders":
            config["tasks"] = self._generate_orders_tasks()
        elif task_type == "feefines":
            config["tasks"] = self._generate_feefines_tasks()

        # Save task config
        task_path = self.tasks_dir / f"{task_type}.json"
        task_path.write_text(
            json.dumps(config, indent=4, ensure_ascii=False), encoding="utf-8"
        )

        return config

    def generate_all_task_configs(self):
        """Generate all task configuration files."""
        self.ensure_directories()
        for task_type in TASK_DEFINITIONS:
            self.generate_task_config(task_type)

    def generate_mapping_templates(self):
        """Generate template mapping files."""
        self.ensure_directories()

        # Location mapping template
        self._write_tsv_template(
            "locations.tsv",
            ["legacy_code", "folio_code"],
            [["MAIN", "main/stacks"], ["REF", "main/reference"]],
        )

        # Material types mapping template
        # Column "folio_name" is required by folio_migration_tools RefDataMapping.
        # Column "MATERIAL_TYPE" must match the source data TSV column name.
        self._write_tsv_template(
            "material_types.tsv",
            ["folio_name", "MATERIAL_TYPE"],
            [["book", "BOOK"], ["dvd", "DVD"], ["sound recording", "CD"], ["book", "*"]],
        )

        # Loan types mapping template
        # Column "folio_name" is required by folio_migration_tools RefDataMapping.
        # Column "LOAN_TYPE" must match the source data TSV column name.
        # The "*" row is the fallback for unmatched/empty values.
        self._write_tsv_template(
            "loan_types.tsv",
            ["folio_name", "LOAN_TYPE"],
            [["Can circulate", "REGULAR"], ["Course reserves", "RESERVE"], ["Can circulate", "*"]],
        )

        # User groups mapping template
        self._write_tsv_template(
            "user_groups.tsv",
            ["legacy_code", "folio_name"],
            [
                ["STUDENT", "undergraduate"],
                ["GRAD", "graduate"],
                ["FACULTY", "faculty"],
                ["STAFF", "staff"],
            ],
        )

        # Item statuses mapping template
        # ItemsTransformer requires columns "legacy_code" and "folio_name" (exact names).
        # Do NOT use "*" wildcard - the tool rejects it for status mapping.
        self._write_tsv_template(
            "item_statuses.tsv",
            ["legacy_code", "folio_name"],
            [
                ["Available", "Available"],
                ["Checked out", "Checked out"],
                ["Missing", "Missing"],
                ["Declared lost", "Declared lost"],
            ],
        )

        # Call number type mapping template
        # Column "folio_name" is required by folio_migration_tools RefDataMapping.
        # Column "CALL_NUMBER_TYPE" must match the source data TSV column name.
        # The "*" row is the fallback for unmatched values (required).
        self._write_tsv_template(
            "call_number_type_mapping.tsv",
            ["folio_name", "CALL_NUMBER_TYPE"],
            [
                ["Library of Congress classification", "LCC"],
                ["Dewey Decimal classification", "DDC"],
                ["Other scheme", "*"],
            ],
        )

        # User mapping JSON template (folio_migration_tools format)
        self._write_json_template(
            "user_mapping.json",
            {
                "data": [
                    {"folio_field": "barcode", "legacy_field": "BARCODE", "value": "", "description": ""},
                    {"folio_field": "externalSystemId", "legacy_field": "USERNAME", "value": "", "description": ""},
                    {"folio_field": "legacyIdentifier", "legacy_field": "PATRON_ID", "value": "", "description": ""},
                    {"folio_field": "patronGroup", "legacy_field": "PATRON_TYPE", "value": "", "description": ""},
                    {"folio_field": "expirationDate", "legacy_field": "EXPIRY_DATE", "value": "", "description": ""},
                    {"folio_field": "personal.email", "legacy_field": "EMAIL", "value": "", "description": ""},
                    {"folio_field": "personal.firstName", "legacy_field": "FIRST_NAME", "value": "", "description": ""},
                    {"folio_field": "personal.lastName", "legacy_field": "LAST_NAME", "value": "", "description": ""},
                    {"folio_field": "personal.middleName", "legacy_field": "Not mapped", "value": "", "description": ""},
                    {"folio_field": "personal.phone", "legacy_field": "PHONE", "value": "", "description": ""},
                    {"folio_field": "personal.mobilePhone", "legacy_field": "MOBILE", "value": "", "description": ""},
                    {"folio_field": "personal.addresses[0].addressLine1", "legacy_field": "ADDRESS1", "value": "", "description": ""},
                    {"folio_field": "personal.addresses[0].addressLine2", "legacy_field": "ADDRESS2", "value": "", "description": ""},
                    {"folio_field": "personal.addresses[0].city", "legacy_field": "CITY", "value": "", "description": ""},
                    {"folio_field": "personal.addresses[0].postalCode", "legacy_field": "ZIP", "value": "", "description": ""},
                    {"folio_field": "personal.addresses[0].addressTypeId", "legacy_field": "Not mapped", "value": "", "description": ""},
                    {"folio_field": "username", "legacy_field": "USERNAME", "value": "", "description": ""},
                ]
            },
        )

        # Item mapping JSON template (folio_migration_tools format)
        self._write_json_template(
            "item_mapping.json",
            {
                "data": [
                    {"folio_field": "barcode", "legacy_field": "BARCODE", "value": "", "description": "Item barcode"},
                    {"folio_field": "legacyIdentifier", "legacy_field": "ITEM_ID", "value": "", "description": "Legacy item ID"},
                    {"folio_field": "formerIds[0]", "legacy_field": "ITEM_ID", "value": "", "description": "Preserve legacy item ID"},
                    {"folio_field": "formerIds[1]", "legacy_field": "BIB_ID", "value": "", "description": "Preserve legacy bib ID"},
                    {"folio_field": "hrid", "legacy_field": "Not mapped", "value": "", "description": "Human readable ID"},
                    {"folio_field": "holdingsRecordId", "legacy_field": "HOLDINGS_ID", "value": "", "description": "Link to holdings"},
                    {"folio_field": "itemLevelCallNumber", "legacy_field": "CALL_NUMBER", "value": "", "description": "Item level call number"},
                    {"folio_field": "materialTypeId", "legacy_field": "MATERIAL_TYPE", "value": "", "description": "Material type"},
                    {"folio_field": "permanentLoanTypeId", "legacy_field": "LOAN_TYPE", "value": "", "description": "Loan type"},
                    {"folio_field": "status.name", "legacy_field": "STATUS", "value": "", "description": "Item status"},
                    {"folio_field": "permanentLocationId", "legacy_field": "LOCATION", "value": "", "description": "Permanent location"},
                    {"folio_field": "temporaryLocationId", "legacy_field": "Not mapped", "value": "", "description": "Temporary location"},
                    {"folio_field": "copyNumber", "legacy_field": "COPY_NUMBER", "value": "", "description": "Copy number"},
                    {"folio_field": "volume", "legacy_field": "Not mapped", "value": "", "description": "Volume"},
                    {"folio_field": "enumeration", "legacy_field": "Not mapped", "value": "", "description": "Enumeration"},
                    {"folio_field": "chronology", "legacy_field": "Not mapped", "value": "", "description": "Chronology"},
                    {"folio_field": "yearCaption[0]", "legacy_field": "YEAR", "value": "", "description": "Year caption"},
                    {"folio_field": "notes[0].note", "legacy_field": "NOTE", "value": "", "description": "Item note"},
                    {"folio_field": "notes[0].itemNoteTypeId", "legacy_field": "Not mapped", "value": "", "description": "Note type UUID - auto-filled from FOLIO"},
                    {"folio_field": "notes[0].staffOnly", "legacy_field": "Not mapped", "value": "false", "description": "Staff only flag"},
                ]
            },
        )

        # Holdings mapping JSON template (folio_migration_tools format)
        self._write_json_template(
            "holdingsrecord_mapping.json",
            {
                "data": [
                    {"folio_field": "legacyIdentifier", "legacy_field": "HOLDINGS_ID", "value": "", "description": "Legacy holdings ID"},
                    {"folio_field": "formerIds[0]", "legacy_field": "HOLDINGS_ID", "value": "", "description": "Preserve legacy holdings ID"},
                    {"folio_field": "instanceId", "legacy_field": "BIB_ID", "value": "", "description": "Link to instance by bib ID"},
                    {"folio_field": "permanentLocationId", "legacy_field": "LOCATION", "value": "", "description": "Permanent location"},
                    {"folio_field": "temporaryLocationId", "legacy_field": "Not mapped", "value": "", "description": "Temporary location"},
                    {"folio_field": "callNumber", "legacy_field": "CALL_NUMBER", "value": "", "description": "Call number"},
                    {"folio_field": "callNumberTypeId", "legacy_field": "CALL_NUMBER_TYPE", "value": "", "description": "Call number type - mapped via call_number_type_mapping.tsv"},
                    {"folio_field": "callNumberPrefix", "legacy_field": "Not mapped", "value": "", "description": "Call number prefix"},
                    {"folio_field": "callNumberSuffix", "legacy_field": "Not mapped", "value": "", "description": "Call number suffix"},
                    {"folio_field": "holdingsTypeId", "legacy_field": "Not mapped", "value": "", "description": "Holdings type UUID"},
                    {"folio_field": "copyNumber", "legacy_field": "Not mapped", "value": "", "description": "Copy number"},
                    {"folio_field": "discoverySuppress", "legacy_field": "Not mapped", "value": "", "description": "Suppress from discovery"},
                    {"folio_field": "notes[0].note", "legacy_field": "NOTE", "value": "", "description": "Holdings note"},
                    {"folio_field": "notes[0].holdingsNoteTypeId", "legacy_field": "Not mapped", "value": "", "description": "Note type UUID - auto-filled from FOLIO"},
                    {"folio_field": "notes[0].staffOnly", "legacy_field": "Not mapped", "value": "false", "description": "Staff only flag"},
                    {"folio_field": "holdingsStatements[0].statement", "legacy_field": "Not mapped", "value": "", "description": "Holdings statement"},
                ]
            },
        )

        # Course mapping JSON template
        self._write_json_template(
            "course_mapping.json",
            {
                "data": [
                    {"folio_field": "courseNumber", "legacy_field": "COURSE_CODE", "value": "", "description": ""},
                    {"folio_field": "name", "legacy_field": "COURSE_NAME", "value": "", "description": ""},
                    {"folio_field": "sectionName", "legacy_field": "SECTION", "value": "", "description": ""},
                    {"folio_field": "termId", "legacy_field": "TERM", "value": "", "description": ""},
                    {"folio_field": "departmentId", "legacy_field": "DEPARTMENT", "value": "", "description": ""},
                    {"folio_field": "courseListingId", "legacy_field": "Not mapped", "value": "", "description": ""},
                ]
            },
        )

        # Terms mapping template
        self._write_tsv_template(
            "terms_map.tsv",
            ["legacy_term", "folio_term_name"],
            [["FALL2024", "Fall 2024"], ["SPRING2025", "Spring 2025"]],
        )

        # Organization mapping JSON template (folio_migration_tools format)
        self._write_json_template(
            "organization_mapping.json",
            {
                "data": [
                    {"folio_field": "legacyIdentifier", "legacy_field": "VENDOR_ID", "value": "", "description": ""},
                    {"folio_field": "name", "legacy_field": "VENDOR_NAME", "value": "", "description": ""},
                    {"folio_field": "code", "legacy_field": "VENDOR_CODE", "value": "", "description": ""},
                    {"folio_field": "status", "legacy_field": "STATUS", "value": "Active", "description": ""},
                    {"folio_field": "isVendor", "legacy_field": "Not mapped", "value": True, "description": ""},
                    {"folio_field": "accounts[0].accountNo", "legacy_field": "ACCOUNT_NO", "value": "", "description": ""},
                    {"folio_field": "accounts[0].accountStatus", "legacy_field": "Not mapped", "value": "Active", "description": ""},
                    {"folio_field": "addresses[0].addressLine1", "legacy_field": "ADDRESS1", "value": "", "description": ""},
                    {"folio_field": "addresses[0].city", "legacy_field": "CITY", "value": "", "description": ""},
                    {"folio_field": "emails[0].value", "legacy_field": "EMAIL", "value": "", "description": ""},
                    {"folio_field": "phoneNumbers[0].phoneNumber", "legacy_field": "PHONE", "value": "", "description": ""},
                ]
            },
        )

        # Order mapping JSON template
        self._write_json_template(
            "composite_order_mapping.json",
            {
                "data": [
                    {"folio_field": "legacyIdentifier", "legacy_field": "PO_NUMBER", "value": "", "description": ""},
                    {"folio_field": "poNumber", "legacy_field": "PO_NUMBER", "value": "", "description": ""},
                    {"folio_field": "vendor", "legacy_field": "VENDOR_CODE", "value": "", "description": ""},
                    {"folio_field": "orderType", "legacy_field": "ORDER_TYPE", "value": "One-Time", "description": ""},
                    {"folio_field": "compositePoLines[0].titleOrPackage", "legacy_field": "TITLE", "value": "", "description": ""},
                    {"folio_field": "compositePoLines[0].cost.listUnitPrice", "legacy_field": "UNIT_PRICE", "value": "", "description": ""},
                    {"folio_field": "compositePoLines[0].cost.quantityPhysical", "legacy_field": "QUANTITY", "value": "", "description": ""},
                    {"folio_field": "compositePoLines[0].cost.currency", "legacy_field": "Not mapped", "value": "USD", "description": ""},
                    {"folio_field": "compositePoLines[0].orderFormat", "legacy_field": "Not mapped", "value": "Physical Resource", "description": ""},
                    {"folio_field": "compositePoLines[0].source", "legacy_field": "Not mapped", "value": "User", "description": ""},
                ]
            },
        )

        # Fee/fine mapping JSON template (folio_migration_tools format)
        self._write_json_template(
            "manual_feefines_map.json",
            {
                "data": [
                    {"folio_field": "legacyIdentifier", "legacy_field": "", "value": "", "description": "Leave this blank."},
                    {"folio_field": "account.amount", "legacy_field": "AMOUNT", "value": "", "description": "The original amount."},
                    {"folio_field": "account.remaining", "legacy_field": "REMAINING", "value": "", "description": "The remaining amount."},
                    {"folio_field": "account.paymentStatus.name", "legacy_field": "", "value": "Outstanding", "description": ""},
                    {"folio_field": "account.status.name", "legacy_field": "", "value": "Open", "description": ""},
                    {"folio_field": "account.userId", "legacy_field": "PATRON_BARCODE", "value": "", "description": "The patron's barcode."},
                    {"folio_field": "account.itemId", "legacy_field": "ITEM_BARCODE", "value": "", "description": "Optional - the barcode of an item."},
                    {"folio_field": "account.feeFineId", "legacy_field": "FEE_TYPE", "value": "", "description": "The fee/fine type."},
                    {"folio_field": "account.ownerId", "legacy_field": "OWNER", "value": "", "description": "The fee/fine owner."},
                    {"folio_field": "feefineaction.dateAction", "legacy_field": "DATE", "value": "", "description": "The date of the fee/fine."},
                ]
            },
        )

        # Fee/fine owners template
        self._write_tsv_template(
            "feefine_owners.tsv",
            ["legacy_owner", "folio_owner"],
            [["MAIN", "Main Library"], ["BRANCH", "Branch Library"]],
        )

        # Fee/fine types template
        self._write_tsv_template(
            "feefine_types.tsv",
            ["legacy_type", "folio_type"],
            [["OVERDUE", "Overdue fine"], ["LOST", "Lost item fee"], ["DAMAGE", "Damaged item"]],
        )

    def _write_tsv_template(
        self, filename: str, headers: list[str], sample_rows: list[list[str]]
    ):
        """Write a TSV template file."""
        filepath = self.mapping_files_dir / filename
        if filepath.exists():
            return  # Don't overwrite existing files

        lines = ["\t".join(headers)]
        for row in sample_rows:
            lines.append("\t".join(row))

        filepath.write_text("\n".join(lines), encoding="utf-8")

    def _write_json_template(self, filename: str, content: dict):
        """Write a JSON template file."""
        filepath = self.mapping_files_dir / filename
        if filepath.exists():
            return  # Don't overwrite existing files

        filepath.write_text(
            json.dumps(content, indent=4, ensure_ascii=False), encoding="utf-8"
        )

    def generate_combined_config(self) -> dict:
        """Generate the combined migration config from all enabled tasks."""
        # Load library config
        library_config_path = self.mapping_files_dir / "library_config.json"
        if not library_config_path.exists():
            return {}

        library_config = json.loads(library_config_path.read_text(encoding="utf-8"))
        combined = {
            "libraryInformation": library_config.get("libraryInformation", {}),
            "migrationTasks": [],
        }

        # Load and merge enabled task configs
        for task_file in sorted(self.tasks_dir.glob("*.json")):
            try:
                task_config = json.loads(task_file.read_text(encoding="utf-8"))
                if task_config.get("enabled", False):
                    combined["migrationTasks"].extend(task_config.get("tasks", []))
            except Exception:
                continue

        # Save combined config
        combined_path = self.mapping_files_dir / "migration_config.json"
        combined_path.write_text(
            json.dumps(combined, indent=4, ensure_ascii=False), encoding="utf-8"
        )

        return combined

    def get_task_config(self, task_type: str) -> Optional[dict]:
        """Get a task configuration."""
        task_path = self.tasks_dir / f"{task_type}.json"
        if not task_path.exists():
            return None
        return json.loads(task_path.read_text(encoding="utf-8"))

    def update_task_config(self, task_type: str, config: dict):
        """Update a task configuration."""
        task_path = self.tasks_dir / f"{task_type}.json"
        task_path.write_text(
            json.dumps(config, indent=4, ensure_ascii=False), encoding="utf-8"
        )
        # Regenerate combined config
        self.generate_combined_config()

    def enable_task(self, task_type: str, enabled: bool = True):
        """Enable or disable a task type."""
        config = self.get_task_config(task_type)
        if config:
            config["enabled"] = enabled
            self.update_task_config(task_type, config)

    def list_mapping_files(self) -> list[dict]:
        """List all mapping files (excludes config files)."""
        files = []
        if self.mapping_files_dir.exists():
            for f in sorted(self.mapping_files_dir.iterdir()):
                if f.is_file() and f.suffix in [".json", ".tsv", ".csv", ".txt"]:
                    # Skip config files
                    if (f.name.endswith("_config.json") or
                        f.name == "library_config.json" or
                        f.name == "migration_config.json"):
                        continue
                    files.append({
                        "filename": f.name,
                        "path": str(f.relative_to(self.client_path)),
                        "size": f.stat().st_size,
                        "type": "json" if f.suffix == ".json" else "tsv",
                    })
        return files

    # Task generation methods
    def _generate_bibs_tasks(self) -> list[dict]:
        return [
            {
                "name": "transform_bibs",
                "migrationTaskType": "BibsTransformer",
                "addAdministrativeNotesWithLegacyIds": True,
                "hridHandling": "default",
                "ilsFlavour": "tag001",
                "tags_to_delete": [],
                "files": [{"file_name": "bibs.mrc", "discovery_suppressed": False}],
                "updateHridSettings": False,
            },
            {
                "name": "post_instances",
                "migrationTaskType": "BatchPoster",
                "objectType": "Instances",
                "batchSize": 250,
                "files": [{"file_name": "folio_instances_transform_bibs.json"}],
            },
            {
                "name": "post_srs_bibs",
                "migrationTaskType": "BatchPoster",
                "objectType": "SRS",
                "batchSize": 250,
                "files": [{"file_name": "folio_srs_instances_transform_bibs.json"}],
            },
        ]

    def _generate_authorities_tasks(self) -> list[dict]:
        return [
            {
                "name": "transform_authorities",
                "migrationTaskType": "AuthorityTransformer",
                "ilsFlavour": "tag001",
                "tags_to_delete": [],
                "files": [{"file_name": "authorities.mrc"}],
            },
            {
                "name": "post_authorities",
                "migrationTaskType": "BatchPoster",
                "objectType": "Authorities",
                "batchSize": 250,
                "files": [{"file_name": "folio_authorities_transform_authorities.json"}],
            },
            {
                "name": "post_srs_authorities",
                "migrationTaskType": "BatchPoster",
                "objectType": "SRS",
                "batchSize": 250,
                "files": [{"file_name": "folio_srs_authorities_transform_authorities.json"}],
            },
        ]

    def _generate_holdings_marc_tasks(self) -> list[dict]:
        return [
            {
                "name": "transform_holdings_marc",
                "migrationTaskType": "HoldingsMarcTransformer",
                "legacyIdMarcPath": "001",
                "locationMapFileName": "locations.tsv",
                "defaultCallNumberTypeName": "Library of Congress classification",
                "fallbackHoldingsTypeId": "03c9c400-b9e3-4a07-ac0e-05ab470233ed",
                "hridHandling": "preserve001",
                "createSourceRecords": True,
                "files": [{"file_name": "holdings.mrc", "discovery_suppressed": False}],
                "updateHridSettings": False,
            },
            {
                "name": "post_holdings_marc",
                "migrationTaskType": "BatchPoster",
                "objectType": "Holdings",
                "batchSize": 250,
                "files": [{"file_name": "folio_holdings_transform_holdings_marc.json"}],
            },
            {
                "name": "post_srs_holdings",
                "migrationTaskType": "BatchPoster",
                "objectType": "SRS",
                "batchSize": 250,
                "files": [{"file_name": "folio_srs_holdings_transform_holdings_marc.json"}],
            },
        ]

    def _generate_holdings_csv_tasks(self) -> list[dict]:
        return [
            {
                "name": "transform_holdings_csv",
                "migrationTaskType": "HoldingsCsvTransformer",
                "holdingsMapFileName": "holdingsrecord_mapping.json",
                "locationMapFileName": "locations.tsv",
                "callNumberTypeMapFileName": "call_number_type_mapping.tsv",
                "defaultCallNumberTypeName": "Library of Congress classification",
                "fallbackHoldingsTypeId": "03c9c400-b9e3-4a07-ac0e-05ab470233ed",
                "hridHandling": "default",
                "files": [{"file_name": "holdings.tsv"}],
                "updateHridSettings": False,
            },
            {
                "name": "post_holdings_csv",
                "migrationTaskType": "BatchPoster",
                "objectType": "Holdings",
                "batchSize": 250,
                "files": [{"file_name": "folio_holdings_transform_holdings_csv.json"}],
            },
        ]

    def _generate_items_tasks(self) -> list[dict]:
        return [
            {
                "name": "transform_items",
                "migrationTaskType": "ItemsTransformer",
                "itemsMappingFileName": "item_mapping.json",
                "locationMapFileName": "locations.tsv",
                "materialTypesMapFileName": "material_types.tsv",
                "loanTypesMapFileName": "loan_types.tsv",
                "itemStatusesMapFileName": "item_statuses.tsv",
                "callNumberTypeMapFileName": "call_number_type_mapping.tsv",
                "defaultCallNumberTypeName": "Library of Congress classification",
                "defaultLoanTypeName": "Can circulate",
                "hridHandling": "default",
                "files": [{"file_name": "items.tsv"}],
                "updateHridSettings": False,
            },
            {
                "name": "post_items",
                "migrationTaskType": "BatchPoster",
                "objectType": "Items",
                "batchSize": 250,
                "files": [{"file_name": "folio_items_transform_items.json"}],
            },
        ]

    def _generate_users_tasks(self) -> list[dict]:
        return [
            {
                "name": "transform_users",
                "migrationTaskType": "UserTransformer",
                "userMappingFileName": "user_mapping.json",
                "groupMapPath": "user_groups.tsv",
                "useGroupMap": True,
                "userFile": {"file_name": "users.tsv"},
            },
            {
                "name": "post_users",
                "migrationTaskType": "BatchPoster",
                "objectType": "Users",
                "batchSize": 250,
                "files": [{"file_name": "folio_users_transform_users.json"}],
            },
            {
                "name": "post_extradata_users",
                "migrationTaskType": "BatchPoster",
                "objectType": "Extradata",
                "batchSize": 250,
                "files": [{"file_name": "extradata_transform_users.extradata"}],
            },
        ]

    def _generate_loans_tasks(self) -> list[dict]:
        return [
            {
                "name": "migrate_loans",
                "migrationTaskType": "LoansMigrator",
                "fallbackServicePointId": "",
                "openLoansFiles": [{"file_name": "loans.tsv", "service_point_id": ""}],
                "startingRow": 1,
            }
        ]

    def _generate_requests_tasks(self) -> list[dict]:
        return [
            {
                "name": "migrate_requests",
                "migrationTaskType": "RequestsMigrator",
                "openRequestsFile": {"file_name": "requests.tsv"},
                "item_files": [{"file_name": "folio_items_transform_items.json"}],
                "patron_files": [{"file_name": "folio_users_transform_users.json"}],
            }
        ]

    def _generate_courses_tasks(self) -> list[dict]:
        return [
            {
                "name": "migrate_courses",
                "migrationTaskType": "CoursesMigrator",
                "compositeCourseMapPath": "course_mapping.json",
                "coursesFile": {"fileName": "courses.tsv"},
                "termsMapPath": "terms_map.tsv",
            },
            {
                "name": "post_courses",
                "migrationTaskType": "BatchPoster",
                "objectType": "Extradata",
                "batchSize": 1,
                "files": [{"file_name": "extradata_migrate_courses.extradata"}],
            },
        ]

    def _generate_reserves_tasks(self) -> list[dict]:
        return [
            {
                "name": "migrate_reserves",
                "migrationTaskType": "ReservesMigrator",
                "locationMapPath": "reserve_locations.tsv",
                "courseReserveFilePath": {"fileName": "reserves.tsv"},
            }
        ]

    def _generate_organizations_tasks(self) -> list[dict]:
        return [
            {
                "name": "transform_organizations",
                "migrationTaskType": "OrganizationTransformer",
                "organizationMapPath": "organization_mapping.json",
                "organizationTypesMapPath": "organization_types.tsv",
                "addressCategoriesMapPath": "address_categories.tsv",
                "emailCategoriesMapPath": "email_categories.tsv",
                "phoneCategoriesMapPath": "phone_categories.tsv",
                "files": [{"file_name": "organizations.tsv"}],
            }
        ]

    def _generate_orders_tasks(self) -> list[dict]:
        return [
            {
                "name": "transform_orders",
                "migrationTaskType": "OrdersTransformer",
                "ordersMappingFileName": "composite_order_mapping.json",
                "acquisitionMethodMapFileName": "acquisition_method_map.tsv",
                "organizationsCodeMapFileName": "organization_code_map.tsv",
                "files": [{"fileName": "orders.tsv"}],
            }
        ]

    def _generate_feefines_tasks(self) -> list[dict]:
        return [
            {
                "name": "transform_feefines",
                "migrationTaskType": "ManualFeeFinesTransformer",
                "feefinesMap": "manual_feefines_map.json",
                "feefinesOwnerMap": "feefine_owners.tsv",
                "feefinesTypeMap": "feefine_types.tsv",
                "files": [{"file_name": "feefines.tsv"}],
            },
            {
                "name": "post_feefines",
                "migrationTaskType": "BatchPoster",
                "objectType": "Extradata",
                "batchSize": 1,
                "files": [{"file_name": "extradata_transform_feefines.extradata"}],
            },
        ]

    async def fetch_folio_reference_data(
        self,
        folio_url: str,
        tenant_id: str,
        username: str,
        password: str,
    ) -> dict:
        """Fetch reference data from FOLIO API and return UUIDs.

        Returns:
            dict with keys: holdings_note_type_id, item_note_type_id, etc.
        """
        result = {
            "holdings_note_type_id": "",
            "item_note_type_id": "",
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Authenticate
                auth_url = f"{folio_url.rstrip('/')}/authn/login"
                headers = {
                    "Content-Type": "application/json",
                    "x-okapi-tenant": tenant_id,
                }
                payload = {"username": username, "password": password}

                response = await client.post(auth_url, json=payload, headers=headers)

                if response.status_code not in (200, 201):
                    return result

                # Get token
                token = response.headers.get("x-okapi-token")
                if not token:
                    body = response.json()
                    token = body.get("okapiToken") or body.get("accessToken")

                if not token:
                    return result

                auth_headers = {
                    "x-okapi-tenant": tenant_id,
                    "x-okapi-token": token,
                    "Content-Type": "application/json",
                }

                # Fetch holdings note types
                note_types_url = f"{folio_url.rstrip('/')}/holdings-note-types?limit=100"
                response = await client.get(note_types_url, headers=auth_headers)

                if response.status_code == 200:
                    data = response.json()
                    for note_type in data.get("holdingsNoteTypes", []):
                        if note_type.get("name") == "Note":
                            result["holdings_note_type_id"] = note_type.get("id", "")
                            break

                # Fetch item note types
                item_note_types_url = f"{folio_url.rstrip('/')}/item-note-types?limit=100"
                response = await client.get(item_note_types_url, headers=auth_headers)

                if response.status_code == 200:
                    data = response.json()
                    for note_type in data.get("itemNoteTypes", []):
                        if note_type.get("name") == "Note":
                            result["item_note_type_id"] = note_type.get("id", "")
                            break

        except Exception:
            pass

        return result

    def update_mapping_with_reference_data(self, reference_data: dict):
        """Update mapping files with reference data UUIDs from FOLIO.

        Args:
            reference_data: dict with holdings_note_type_id, item_note_type_id, etc.
        """
        # Update holdingsrecord_mapping.json
        holdings_mapping_path = self.mapping_files_dir / "holdingsrecord_mapping.json"
        if holdings_mapping_path.exists() and reference_data.get("holdings_note_type_id"):
            try:
                mapping = json.loads(holdings_mapping_path.read_text(encoding="utf-8"))
                for item in mapping.get("data", []):
                    if item.get("folio_field") == "notes[0].holdingsNoteTypeId":
                        item["value"] = reference_data["holdings_note_type_id"]
                        break
                holdings_mapping_path.write_text(
                    json.dumps(mapping, indent=4, ensure_ascii=False), encoding="utf-8"
                )
            except Exception:
                pass

        # Update item_mapping.json
        item_mapping_path = self.mapping_files_dir / "item_mapping.json"
        if item_mapping_path.exists() and reference_data.get("item_note_type_id"):
            try:
                mapping = json.loads(item_mapping_path.read_text(encoding="utf-8"))
                for item in mapping.get("data", []):
                    if item.get("folio_field") == "notes[0].itemNoteTypeId":
                        item["value"] = reference_data["item_note_type_id"]
                        break
                item_mapping_path.write_text(
                    json.dumps(mapping, indent=4, ensure_ascii=False), encoding="utf-8"
                )
            except Exception:
                pass


def get_config_service(client_path: Path) -> ConfigService:
    """Get a config service for a client."""
    return ConfigService(client_path)
