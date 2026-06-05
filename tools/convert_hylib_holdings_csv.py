"""Convert HyLib holdings/items CSV (SQL Server export) to FOLIO holdings.tsv + items.tsv.

Replaces extract_095_standard.py for clients that export holdings from the HyLib
`hold` table directly (joined to `marc`), instead of parsing MARC 095 fields.

Usage (on Linux):
    cd /folio/folio_migration_web
    python tools/convert_hylib_holdings_csv.py \
        clients/<client>/iterations/<iter>/source_data/items/<input>.csv \
        clients/<client>/iterations/<iter>/source_data/holdings/holdings.tsv \
        clients/<client>/iterations/<iter>/source_data/items/items.tsv

    Then copy holdings.tsv into source_data/items/ as well (HoldingsCsvTransformer
    has a hardcoded source_data/items/ path).

Source CSV (HyLib hold + marc join). SQL Server CHAR columns are space-padded, so
every value is stripped. The first header carries a UTF-8 BOM -> read utf-8-sig.
    marc_id                     -> BIB_ID (== MARC 001, links to instance)
    hold_id                     -> ITEM_ID (unique, stable; seeds the item UUID)
    barcode                     -> BARCODE (cleared when shared by >1 hold_id)
    keeproom_code               -> LOCATION (-> locations.tsv)
    collection_code             -> MATERIAL_TYPE (-> material_types.tsv)
    class_type                  -> CALL_NUMBER_TYPE (-> call_number_type_mapping.tsv)
    new_holdcallNumber_holding  -> holdings CALL_NUMBER + part of HOLDINGS_ID
    new_holdcallNumber_item     -> item CALL_NUMBER
    description2                -> COPY_NUMBER
    description3                -> YEAR (yearCaption)
    description_final           -> ENUMERATION (e.g. v.263)
    remark                      -> item NOTE (general)
    annex                       -> item CHECKOUT_NOTE (circulationNotes, "Check out")

HOLDINGS_ID = marc_id-keeproom_code-collection_code-new_holdcallNumber_holding
(first three stripped; the call number keeps its internal spaces). Rows that share
this key collapse to one holdings record with multiple items beneath it.
"""

import csv
import sys
from collections import Counter

HOLDINGS_HEADERS = [
    "HOLDINGS_ID",
    "BIB_ID",
    "LOCATION",
    "CALL_NUMBER",
    "CALL_NUMBER_TYPE",
    "NOTE",
]

ITEMS_HEADERS = [
    "ITEM_ID",
    "BARCODE",
    "BIB_ID",
    "HOLDINGS_ID",
    "MATERIAL_TYPE",
    "LOAN_TYPE",
    "LOCATION",
    "CALL_NUMBER",
    "COPY_NUMBER",
    "YEAR",
    "STATUS",
    "ENUMERATION",
    "NOTE",
    "CHECKOUT_NOTE",
]

DEFAULT_STATUS = "Available"


def _s(row, key):
    """Return a field value stripped of CHAR padding (None-safe)."""
    return (row.get(key) or "").strip()


def make_holdings_id(bib, location, material, call_number):
    """Holdings grouping key.

    bib/location/material are already stripped; call_number keeps its internal
    spaces (PM wants the natural call-number format, e.g. '830.51 8054 2006').
    Holdings and items must compute this identically to link.
    """
    return f"{bib}-{location}-{material}-{call_number}"


def convert(input_csv: str, holdings_tsv: str, items_tsv: str) -> dict:
    """Convert HyLib holdings/items CSV to FOLIO holdings.tsv + items.tsv.

    Returns:
        {"holdings": int, "items": int, "skipped": int,
         "cleared_barcodes": int, "warnings": list, "output_files": list}
    """
    # utf-8-sig strips the BOM that sits on the first header.
    with open(input_csv, "r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    # Pass 1: find barcodes shared by more than one item. FOLIO requires unique
    # item barcodes, and HyLib reuses placeholder barcodes across distinct items
    # (e.g. 20200325004). Those are cleared so every item still migrates by
    # hold_id; the barcode can be reassigned later in FOLIO.
    barcode_counts = Counter(bc for r in rows if (bc := _s(r, "barcode")))
    shared_barcodes = {bc for bc, n in barcode_counts.items() if n > 1}

    holdings: dict = {}
    items: list = []
    warnings: list = []
    skipped = 0
    cleared_barcodes = 0

    for row in rows:
        bib = _s(row, "marc_id")
        hold_id = _s(row, "hold_id")
        if not bib or not hold_id:
            warnings.append(f"Skipping row missing marc_id/hold_id: hold_id={hold_id!r} bib={bib!r}")
            skipped += 1
            continue

        location = _s(row, "keeproom_code")
        material = _s(row, "collection_code")
        call_type = _s(row, "class_type")
        call_holding = _s(row, "new_holdcallNumber_holding")
        call_item = _s(row, "new_holdcallNumber_item")

        holdings_id = make_holdings_id(bib, location, material, call_holding)

        if holdings_id not in holdings:
            holdings[holdings_id] = {
                "HOLDINGS_ID": holdings_id,
                "BIB_ID": bib,
                "LOCATION": location,
                "CALL_NUMBER": call_holding,
                "CALL_NUMBER_TYPE": call_type,
                "NOTE": "",
            }

        barcode = _s(row, "barcode")
        if barcode and barcode in shared_barcodes:
            barcode = ""
            cleared_barcodes += 1

        items.append({
            "ITEM_ID": hold_id,
            "BARCODE": barcode,
            "BIB_ID": bib,
            "HOLDINGS_ID": holdings_id,
            "MATERIAL_TYPE": material,
            "LOAN_TYPE": "",  # falls back to defaultLoanTypeName
            "LOCATION": location,
            "CALL_NUMBER": call_item,
            "COPY_NUMBER": _s(row, "description2"),
            "YEAR": _s(row, "description3"),
            "STATUS": DEFAULT_STATUS,
            "ENUMERATION": _s(row, "description_final"),
            "NOTE": _s(row, "remark"),
            "CHECKOUT_NOTE": _s(row, "annex"),
        })

    with open(holdings_tsv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HOLDINGS_HEADERS, delimiter="\t")
        writer.writeheader()
        writer.writerows(holdings.values())

    with open(items_tsv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=ITEMS_HEADERS, delimiter="\t")
        writer.writeheader()
        writer.writerows(items)

    return {
        "holdings": len(holdings),
        "items": len(items),
        "skipped": skipped,
        "cleared_barcodes": cleared_barcodes,
        "warnings": warnings,
        "output_files": [holdings_tsv, items_tsv],
    }


def main():
    if len(sys.argv) < 4:
        print(f"Usage: {sys.argv[0]} <input_csv> <holdings_tsv> <items_tsv>")
        sys.exit(1)
    result = convert(sys.argv[1], sys.argv[2], sys.argv[3])
    print(f"Holdings: {result['holdings']}")
    print(f"Items:    {result['items']}")
    print(f"Skipped:  {result['skipped']}")
    print(f"Cleared (shared) barcodes: {result['cleared_barcodes']}")
    for w in result["warnings"][:20]:
        print(f"  WARN: {w}")


if __name__ == "__main__":
    main()
