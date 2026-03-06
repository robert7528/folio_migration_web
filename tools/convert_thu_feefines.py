"""Convert THU fee/fine CSV to FOLIO feefines.tsv for ManualFeeFinesTransformer.

Usage (on Linux):
    cd /folio/folio_migration_web
    python tools/convert_thu_feefines.py \
        clients/thu/iterations/thu_migration/source_data/fees_fines/thu_feefines-15.csv \
        clients/thu/iterations/thu_migration/source_data/fees_fines/feefines.tsv

Source CSV columns (HyLib):
    reader_code, barcode, total, contribute, insert_date, name, fineTypeId, status

Output TSV columns (FOLIO ManualFeeFinesTransformer):
    amount, remaining, patron_barcode, item_barcode, billed_date, type,
    lending_library, borrowing_desk
"""

import csv
import sys
from datetime import timezone, timedelta

TW_TZ = timezone(timedelta(hours=8))

FEEFINES_TSV_HEADERS = [
    "amount",
    "remaining",
    "patron_barcode",
    "item_barcode",
    "billed_date",
    "type",
    "lending_library",
    "borrowing_desk",
]

# HyLib fineTypeId -> FOLIO fee/fine type name
FINE_TYPE_MAP = {
    "2": "逾期罰金",
}


def convert_datetime(dt_str: str) -> str:
    """Convert 'YYYY-MM-DD HH:MM:SS.fff' to ISO 8601 with +08:00 timezone."""
    dt_str = dt_str.strip()
    date_part, time_part = dt_str.split(" ")
    if "." in time_part:
        main, frac = time_part.split(".")
        frac = frac.ljust(6, "0")
        time_part = f"{main}.{frac}"
    else:
        time_part = f"{time_part}.000000"
    return f"{date_part}T{time_part}+08:00"


def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <input_csv> <output_tsv>")
        sys.exit(1)

    input_csv = sys.argv[1]
    output_tsv = sys.argv[2]

    rows = []
    skipped_paid = 0
    skipped_other = 0

    with open(input_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            status = row.get("status", "").strip()

            # Only migrate unpaid fines (status == 0)
            if status != "0":
                skipped_paid += 1
                continue

            try:
                total = float(row["total"].strip())
                contribute = float(row.get("contribute", "0").strip() or "0")
            except (ValueError, KeyError) as e:
                print(f"WARNING: skipping row with invalid amount: {e}")
                skipped_other += 1
                continue

            remaining = total - contribute
            patron_barcode = row["reader_code"].strip()
            item_barcode = row["barcode"].strip()

            try:
                billed_date = convert_datetime(row["insert_date"])
            except (ValueError, KeyError) as e:
                print(f"WARNING: skipping row with invalid date: {e}")
                skipped_other += 1
                continue

            fine_type_id = row.get("fineTypeId", "").strip()
            fine_type_name = FINE_TYPE_MAP.get(fine_type_id, row.get("name", "").strip())

            rows.append({
                "amount": str(total),
                "remaining": str(remaining),
                "patron_barcode": patron_barcode,
                "item_barcode": item_barcode,
                "billed_date": billed_date,
                "type": fine_type_name,
                "lending_library": "thu",
                "borrowing_desk": "",
            })

    with open(output_tsv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FEEFINES_TSV_HEADERS, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)

    print(f"Converted {len(rows)} unpaid fee/fines to {output_tsv}")
    if skipped_paid:
        print(f"Skipped {skipped_paid} paid/closed records (status != 0)")
    if skipped_other:
        print(f"Skipped {skipped_other} records due to errors")


if __name__ == "__main__":
    main()
