"""Convert HyLib request CSV to FOLIO requests.tsv for RequestsMigrator.

Usage (on Linux):
    cd /folio/folio_migration_web
    python tools/convert_hylib_requests.py \
        clients/<client>/iterations/<iteration>/source_data/requests/<input>.csv \
        clients/<client>/iterations/<iteration>/source_data/requests/requests.tsv \
        config/<client>/mapping_files/keepsite_service_points.tsv

HyLib CSV columns used:
    barcode           -> item_barcode
    readerCode        -> patron_barcode
    bookdate          -> request_date
    validdate         -> request_expiration_date
    pickupKeepSiteId  -> pickup_servicepoint_id (via keepsite mapping)
    note              -> comment
    toReserveType     -> request_type (81/83 -> Hold)
    bookorder         -> queue position (for sorting)
"""

import csv
import sys
from datetime import timezone, timedelta

TW_TZ = timezone(timedelta(hours=8))

REQUESTS_TSV_HEADERS = [
    "item_barcode",
    "patron_barcode",
    "pickup_servicepoint_id",
    "request_date",
    "request_expiration_date",
    "comment",
    "request_type",
]

# HyLib toReserveType -> FOLIO request_type
RESERVE_TYPE_MAP = {
    "81": "Hold",   # 一般預約
    "83": "Hold",   # 通閱預約 (inter-branch hold)
}
DEFAULT_REQUEST_TYPE = "Hold"


def convert_datetime(dt_str: str) -> str:
    """Convert 'YYYY-MM-DD HH:MM:SS.fff' to ISO 8601 with +08:00 timezone."""
    dt_str = dt_str.strip()
    if not dt_str or dt_str == "NULL":
        return ""
    date_part, time_part = dt_str.split(" ")
    if "." in time_part:
        main, frac = time_part.split(".")
        frac = frac.ljust(6, "0")
        time_part = f"{main}.{frac}"
    else:
        time_part = f"{time_part}.000000"
    return f"{date_part}T{time_part}+08:00"


def load_keepsite_mapping(tsv_path: str) -> dict:
    """Load keepsite_id -> service_point_id mapping from TSV file."""
    mapping = {}
    with open(tsv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            mapping[row["keepsite_id"].strip()] = row["service_point_id"].strip()
    return mapping


def convert(input_csv: str, output_tsv: str, keepsite_tsv: str) -> dict:
    """Convert HyLib request CSV to FOLIO requests.tsv.

    Returns:
        {"converted": int, "warnings": list, "output_files": list, ...}
    """
    keepsite_map = load_keepsite_mapping(keepsite_tsv)
    warnings = []

    unmapped = set()
    reserve_types_seen = set()
    rows = []

    with open(input_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            item_barcode = row["barcode"].strip()
            patron_barcode = row["readerCode"].strip()
            request_date = convert_datetime(row["bookdate"])
            expiration_date = convert_datetime(row["validdate"])

            pickup_id = row["pickupKeepSiteId"].strip()
            service_point_id = keepsite_map.get(pickup_id, "")
            if not service_point_id:
                unmapped.add(pickup_id)

            reserve_type = row.get("toReserveType", "").strip()
            reserve_types_seen.add(reserve_type)
            request_type = RESERVE_TYPE_MAP.get(reserve_type, DEFAULT_REQUEST_TYPE)

            note = row.get("note", "").strip()
            if not note or note == "NULL":
                comment = "Migrated from HyLib"
            else:
                comment = f"{note} (migrated from HyLib)"

            rows.append({
                "item_barcode": item_barcode,
                "patron_barcode": patron_barcode,
                "pickup_servicepoint_id": service_point_id,
                "request_date": request_date,
                "request_expiration_date": expiration_date,
                "comment": comment,
                "request_type": request_type,
            })

    # Sort by request_date to preserve queue order
    rows.sort(key=lambda r: r["request_date"])

    if unmapped:
        warnings.append(
            f"Unmapped pickupKeepSiteId values: {sorted(unmapped)}. "
            "Add these to keepsite_service_points.tsv before running migration."
        )

    with open(output_tsv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=REQUESTS_TSV_HEADERS, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)

    return {
        "converted": len(rows),
        "keepsite_mappings": len(keepsite_map),
        "reserve_types_seen": sorted(reserve_types_seen),
        "warnings": warnings,
        "output_files": [output_tsv],
    }


def main():
    if len(sys.argv) < 4:
        print(f"Usage: {sys.argv[0]} <input_csv> <output_tsv> <keepsite_mapping_tsv>")
        sys.exit(1)

    result = convert(sys.argv[1], sys.argv[2], sys.argv[3])

    print(f"Loaded {result['keepsite_mappings']} keepsite -> service point mappings")
    if result["reserve_types_seen"]:
        print(f"Reserve types seen: {result['reserve_types_seen']}")
    print(f"Converted {result['converted']} requests to {sys.argv[2]}")
    for w in result["warnings"]:
        print(f"WARNING: {w}")


if __name__ == "__main__":
    main()
