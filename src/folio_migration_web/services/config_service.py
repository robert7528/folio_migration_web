"""Configuration file management service.

This module handles:
- Generation of task-specific configuration files
- Generation of mapping file templates
- Merging configs into a single migration config
- Syncing libraryInformation when project info changes
"""

import json
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
        self.mappings_dir = self.mapping_files_dir / "mappings"

    def ensure_directories(self):
        """Create necessary directories."""
        self.mapping_files_dir.mkdir(parents=True, exist_ok=True)
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self.mappings_dir.mkdir(parents=True, exist_ok=True)

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
        self._write_tsv_template(
            "material_types.tsv",
            ["legacy_code", "folio_name"],
            [["BOOK", "book"], ["DVD", "dvd"], ["CD", "sound recording"]],
        )

        # Loan types mapping template
        self._write_tsv_template(
            "loan_types.tsv",
            ["legacy_code", "folio_name"],
            [["REGULAR", "Can circulate"], ["RESERVE", "Course reserves"]],
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
        self._write_tsv_template(
            "item_statuses.tsv",
            ["legacy_status", "folio_status"],
            [
                ["AVAILABLE", "Available"],
                ["CHECKED_OUT", "Checked out"],
                ["MISSING", "Missing"],
                ["LOST", "Declared lost"],
            ],
        )

        # Call number type mapping template
        self._write_tsv_template(
            "call_number_type_mapping.tsv",
            ["legacy_type", "folio_name"],
            [
                ["LC", "Library of Congress classification"],
                ["DEWEY", "Dewey Decimal classification"],
                ["LOCAL", "Other scheme"],
            ],
        )

        # User mapping JSON template
        self._write_json_template(
            "user_mapping.json",
            {
                "legacy_id_field": "patron_id",
                "username_field": "username",
                "barcode_field": "barcode",
                "email_field": "email",
                "firstName_field": "first_name",
                "lastName_field": "last_name",
                "expirationDate_field": "expiry_date",
                "patronGroup_field": "patron_type",
            },
        )

        # Item mapping JSON template
        self._write_json_template(
            "item_mapping.json",
            {
                "legacy_id_field": "item_id",
                "barcode_field": "barcode",
                "callNumber_field": "call_number",
                "materialType_field": "material_type",
                "permanentLoanType_field": "loan_type",
                "status_field": "status",
                "permanentLocation_field": "location",
            },
        )

        # Holdings mapping JSON template
        self._write_json_template(
            "holdingsrecord_mapping.json",
            {
                "legacy_id_field": "holdings_id",
                "instanceId_field": "bib_id",
                "callNumber_field": "call_number",
                "permanentLocation_field": "location",
            },
        )

        # Course mapping JSON template
        self._write_json_template(
            "course_mapping.json",
            {
                "course_number_field": "course_code",
                "course_name_field": "course_name",
                "instructor_field": "instructor",
                "term_field": "term",
                "department_field": "department",
            },
        )

        # Terms mapping template
        self._write_tsv_template(
            "terms_map.tsv",
            ["legacy_term", "folio_term_name"],
            [["FALL2024", "Fall 2024"], ["SPRING2025", "Spring 2025"]],
        )

        # Organization mapping JSON template
        self._write_json_template(
            "organization_mapping.json",
            {
                "legacy_id_field": "vendor_id",
                "name_field": "vendor_name",
                "code_field": "vendor_code",
                "status_field": "status",
            },
        )

        # Order mapping JSON template
        self._write_json_template(
            "composite_order_mapping.json",
            {
                "order_number_field": "po_number",
                "vendor_field": "vendor_code",
                "order_type_field": "order_type",
                "title_field": "title",
                "quantity_field": "quantity",
                "price_field": "unit_price",
            },
        )

        # Fee/fine mapping JSON template
        self._write_json_template(
            "manual_feefines_map.json",
            {
                "user_barcode_field": "patron_barcode",
                "item_barcode_field": "item_barcode",
                "fee_type_field": "fine_type",
                "amount_field": "amount",
                "date_field": "fine_date",
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
        filepath = self.mappings_dir / filename
        if filepath.exists():
            return  # Don't overwrite existing files

        lines = ["\t".join(headers)]
        for row in sample_rows:
            lines.append("\t".join(row))

        filepath.write_text("\n".join(lines), encoding="utf-8")

    def _write_json_template(self, filename: str, content: dict):
        """Write a JSON template file."""
        filepath = self.mappings_dir / filename
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
        """List all mapping files."""
        files = []
        if self.mappings_dir.exists():
            for f in sorted(self.mappings_dir.iterdir()):
                if f.is_file():
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
                "defaultCallNumberTypeName": "Library of Congress classification",
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
                "item_files": [{"file_name": "folio_items_transform_items.json"}],
                "patron_files": [{"file_name": "folio_users_transform_users.json"}],
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


def get_config_service(client_path: Path) -> ConfigService:
    """Get a config service for a client."""
    return ConfigService(client_path)
