"""Convert THU loan CSV to FOLIO loans.tsv for LoansMigrator.

Usage (on Linux):
    cd /folio/folio_migration_web
    python tools/convert_thu_loans.py \
        clients/thu/iterations/thu_migration/source_data/loans/thu_loan.csv \
        clients/thu/iterations/thu_migration/source_data/loans/loans.tsv \
        config/thu/mapping_files/keepsite_service_points.tsv
"""

import csv
import sys
from datetime import timezone, timedelta

TW_TZ = timezone(timedelta(hours=8))

LOANS_TSV_HEADERS = [
    "item_barcode",
    "patron_barcode",
    "due_date",
    "out_date",
    "renewal_count",
    "next_item_status",
    "service_point_id",
]


def convert_datetime(dt_str: str) -> str:
    """Convert 'YYYY-MM-DD HH:MM:SS.fff' to ISO 8601 with +08:00 timezone."""
    # Input:  2026-01-16 16:18:18.287
    # Output: 2026-01-16T16:18:18.287000+08:00
    dt_str = dt_str.strip()
    # Split date and time
    date_part, time_part = dt_str.split(" ")
    # Ensure microseconds (pad milliseconds to 6 digits)
    if "." in time_part:
        main, frac = time_part.split(".")
        frac = frac.ljust(6, "0")
        time_part = f"{main}.{frac}"
    else:
        time_part = f"{time_part}.000000"
    return f"{date_part}T{time_part}+08:00"


def load_keepsite_mapping(tsv_path: str) -> dict:
    """Load lendKeepSiteId -> service_point_id mapping from TSV file."""
    mapping = {}
    with open(tsv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            mapping[row["keepsite_id"].strip()] = row["service_point_id"].strip()
    return mapping


def main():
    if len(sys.argv) < 4:
        print(f"Usage: {sys.argv[0]} <input_csv> <output_tsv> <keepsite_mapping_tsv>")
        sys.exit(1)

    input_csv = sys.argv[1]
    output_tsv = sys.argv[2]
    keepsite_tsv = sys.argv[3]

    keepsite_map = load_keepsite_mapping(keepsite_tsv)
    print(f"Loaded {len(keepsite_map)} keepsite -> service point mappings")

    unmapped = set()
    rows = []
    with open(input_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            item_barcode = row["barcode"].strip()
            patron_barcode = row["readerCode"].strip()
            due_date = convert_datetime(row["returndate"])
            out_date = convert_datetime(row["lenddate"])
            renewal_count = row["continueNum"].strip()
            keepsite_id = row["lendKeepSiteId"].strip()
            service_point_id = keepsite_map.get(keepsite_id, "")
            if not service_point_id:
                unmapped.add(keepsite_id)
            rows.append({
                "item_barcode": item_barcode,
                "patron_barcode": patron_barcode,
                "due_date": due_date,
                "out_date": out_date,
                "renewal_count": renewal_count,
                "next_item_status": "",
                "service_point_id": service_point_id,
            })

    if unmapped:
        print(f"WARNING: unmapped lendKeepSiteId values: {sorted(unmapped)}")

    with open(output_tsv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=LOANS_TSV_HEADERS, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)

    print(f"Converted {len(rows)} loans to {output_tsv}")


if __name__ == "__main__":
    main()
