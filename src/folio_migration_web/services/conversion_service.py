"""Data conversion service.

Wraps the CLI conversion tools (tools/) for use by the web portal,
allowing PMs to convert HyLib source data to FOLIO-compatible TSV
without command-line access.
"""

import shutil
import sys
from pathlib import Path

from ..config import get_settings

settings = get_settings()

# Base directory of the project (repo root)
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent

# Add tools/ to import path so we can import conversion scripts
_tools_dir = str(BASE_DIR / "tools")
if _tools_dir not in sys.path:
    sys.path.insert(0, _tools_dir)

# Conversion type definitions
CONVERSION_TYPES = {
    "feefines": {
        "label": "Fee/Fines (HyLib CSV → feefines.tsv)",
        "accept": ".csv",
        "source_folder": "fees_fines",
        "output_filename": "feefines.tsv",
        "needs_keepsite": False,
    },
    "loans": {
        "label": "Loans (HyLib CSV → loans.tsv)",
        "accept": ".csv",
        "source_folder": "loans",
        "output_filename": "loans.tsv",
        "needs_keepsite": True,
    },
    "requests": {
        "label": "Requests (HyLib CSV → requests.tsv)",
        "accept": ".csv",
        "source_folder": "requests",
        "output_filename": "requests.tsv",
        "needs_keepsite": True,
    },
    "marc_095": {
        "label": "MARC 095 Extract (MRC → holdings.tsv + items.tsv)",
        "accept": ".mrc,.marc,.iso",
        "source_folder": "instances",
        "output_filename": "holdings.tsv + items.tsv",
        "needs_keepsite": False,
    },
}


class ConversionService:
    """Service for converting source data files."""

    def __init__(self, client_code: str):
        self.client_code = client_code
        self.clients_dir = settings.clients_dir
        self.config_dir = BASE_DIR / "config" / client_code / "mapping_files"

    def get_iterations(self) -> list[str]:
        """Get available iterations for this client."""
        iter_path = self.clients_dir / self.client_code / "iterations"
        if not iter_path.exists():
            return []
        return sorted(
            d.name for d in iter_path.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        )

    def get_source_data_path(self, iteration: str, folder: str) -> Path:
        """Get path to a source_data subfolder."""
        return (
            self.clients_dir / self.client_code / "iterations" / iteration
            / "source_data" / folder
        )

    def check_keepsite_mapping(self) -> dict:
        """Check if keepsite_service_points.tsv exists and return info."""
        tsv_path = self.config_dir / "keepsite_service_points.tsv"
        if not tsv_path.exists():
            return {"exists": False, "path": str(tsv_path), "count": 0}

        # Count mappings (header line excluded)
        count = 0
        with open(tsv_path, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i > 0 and line.strip():
                    count += 1
        return {"exists": True, "path": str(tsv_path), "count": count}

    def convert(
        self,
        iteration: str,
        conversion_type: str,
        uploaded_file_path: str,
    ) -> dict:
        """Run conversion and return result dict.

        Args:
            iteration: Iteration name (e.g. "thu_migration")
            conversion_type: One of CONVERSION_TYPES keys
            uploaded_file_path: Path to the uploaded temp file

        Returns:
            dict with conversion results, warnings, output_files, etc.
        """
        if conversion_type not in CONVERSION_TYPES:
            return {"status": "error", "message": f"Unknown conversion type: {conversion_type}"}

        type_def = CONVERSION_TYPES[conversion_type]
        source_dir = self.get_source_data_path(iteration, type_def["source_folder"])
        source_dir.mkdir(parents=True, exist_ok=True)

        try:
            if conversion_type == "feefines":
                return self._convert_feefines(uploaded_file_path, source_dir)
            elif conversion_type == "loans":
                return self._convert_loans(uploaded_file_path, source_dir)
            elif conversion_type == "requests":
                return self._convert_requests(uploaded_file_path, source_dir)
            elif conversion_type == "marc_095":
                return self._convert_marc_095(uploaded_file_path, iteration)
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _convert_feefines(self, input_path: str, source_dir: Path) -> dict:
        """Convert HyLib fee/fine CSV."""
        from convert_hylib_feefines import convert

        output_path = str(source_dir / "feefines.tsv")
        result = convert(input_path, output_path, self.client_code)
        result["status"] = "success"
        return result

    def _convert_loans(self, input_path: str, source_dir: Path) -> dict:
        """Convert HyLib loan CSV."""
        keepsite_path = self.config_dir / "keepsite_service_points.tsv"
        if not keepsite_path.exists():
            return {
                "status": "error",
                "message": (
                    f"keepsite_service_points.tsv not found at {keepsite_path}. "
                    "Please upload it to config mapping files first."
                ),
            }

        from convert_hylib_loans import convert

        output_path = str(source_dir / "loans.tsv")
        result = convert(input_path, output_path, str(keepsite_path))
        result["status"] = "success"
        return result

    def _convert_requests(self, input_path: str, source_dir: Path) -> dict:
        """Convert HyLib request CSV."""
        keepsite_path = self.config_dir / "keepsite_service_points.tsv"
        if not keepsite_path.exists():
            return {
                "status": "error",
                "message": (
                    f"keepsite_service_points.tsv not found at {keepsite_path}. "
                    "Please upload it to config mapping files first."
                ),
            }

        from convert_hylib_requests import convert

        output_path = str(source_dir / "requests.tsv")
        result = convert(input_path, output_path, str(keepsite_path))
        result["status"] = "success"
        return result

    def _convert_marc_095(self, input_path: str, iteration: str) -> dict:
        """Convert MARC 095 to holdings + items TSV."""
        holdings_dir = self.get_source_data_path(iteration, "holdings")
        items_dir = self.get_source_data_path(iteration, "items")
        holdings_dir.mkdir(parents=True, exist_ok=True)
        items_dir.mkdir(parents=True, exist_ok=True)

        from extract_095_standard import convert

        holdings_output = str(holdings_dir / "holdings.tsv")
        items_output = str(items_dir / "items.tsv")

        result = convert(input_path, holdings_output, items_output)

        # Workaround: folio_migration_tools bug — HoldingsCsvTransformer
        # looks in source_data/items/ instead of source_data/holdings/
        workaround_path = items_dir / "holdings.tsv"
        if Path(holdings_output).exists():
            shutil.copy2(holdings_output, workaround_path)
            result["warnings"].append(
                "holdings.tsv also copied to source_data/items/ "
                "(workaround for folio_migration_tools HoldingsCsvTransformer bug)"
            )
            result["output_files"].append(str(workaround_path))

        result["status"] = "success"
        return result
