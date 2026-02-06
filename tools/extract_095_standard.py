#!/usr/bin/env python3
"""
Extract 095 field from MARC records and generate Holdings/Items TSV files.

This version outputs column names that match the default folio_migration_web
mapping templates (holdingsrecord_mapping.json, item_mapping.json).

Usage:
    python extract_095_standard.py input.mrc [holdings_output.tsv] [items_output.tsv]

Example:
    python extract_095_standard.py source_data/instances/bibs.mrc

Output:
    - holdings.tsv (columns: HOLDINGS_ID, BIB_ID, LOCATION, CALL_NUMBER, NOTE)
    - items.tsv (columns: ITEM_ID, BIB_ID, HOLDINGS_ID, BARCODE, LOCATION, MATERIAL_TYPE, LOAN_TYPE, CALL_NUMBER, COPY_NUMBER, YEAR, NOTE)
"""

import sys
import csv
from pathlib import Path

try:
    from pymarc import MARCReader
except ImportError:
    print("ERROR: pymarc not installed. Run: pip install pymarc")
    sys.exit(1)


def extract_095_data(marc_file):
    """Extract 095 field data from MARC file."""
    records_data = []
    record_count = 0
    records_with_095 = 0
    item_counter = 0

    print(f"Reading MARC file: {marc_file}")

    with open(marc_file, 'rb') as f:
        reader = MARCReader(f)
        for record in reader:
            record_count += 1
            bib_id = record['001'].data.strip() if record['001'] else None
            if not bib_id:
                continue

            fields_095 = record.get_fields('095')
            if not fields_095:
                continue

            records_with_095 += 1

            for f095 in fields_095:
                item_counter += 1
                data = {
                    'bib_id': bib_id,
                    'library': '',           # $a
                    'location': '',          # $b
                    'barcode': '',           # $c
                    'classification': '',    # $d
                    'cutter': '',            # $e
                    'material_type': '',     # $p
                    'price': '',             # $r
                    'date': '',              # $s
                    'call_number_type': '',  # $t
                    'year': '',              # $y
                    'full_call_number': '',  # $z
                    'item_id': f"ITEM-{item_counter:08d}",  # Generated unique ID
                }

                for subfield in f095:
                    code, value = subfield[0], subfield[1].strip()
                    if code == 'a':
                        data['library'] = value
                    elif code == 'b':
                        data['location'] = value
                    elif code == 'c':
                        data['barcode'] = value
                    elif code == 'd':
                        data['classification'] = value
                    elif code == 'e':
                        data['cutter'] = value
                    elif code == 'p':
                        data['material_type'] = value
                    elif code == 'r':
                        data['price'] = value
                    elif code == 's':
                        data['date'] = value
                    elif code == 't':
                        data['call_number_type'] = value
                    elif code == 'y':
                        data['year'] = value
                    elif code == 'z':
                        data['full_call_number'] = value

                # Build call number if not provided in $z
                if not data['full_call_number'] and data['classification']:
                    parts = [data['classification']]
                    if data['cutter']:
                        parts.append(data['cutter'])
                    if data['year']:
                        parts.append(data['year'])
                    data['full_call_number'] = ' '.join(parts)

                # Use barcode as item_id if available
                if data['barcode']:
                    data['item_id'] = data['barcode']

                records_data.append(data)

    print(f"Total MARC records: {record_count}")
    print(f"Records with 095: {records_with_095}")
    print(f"Total 095 fields (items): {len(records_data)}")

    return records_data


def generate_holdings_id(bib_id, location, call_number):
    """Generate a unique holdings ID based on bib_id + location + call_number."""
    # Create a simple hash-like ID
    combined = f"{bib_id}-{location}-{call_number}"
    return combined.replace(' ', '_').replace('/', '-')[:50]


def write_holdings_tsv(records_data, output_file):
    """
    Write holdings TSV file with standard column names.

    Columns match default holdingsrecord_mapping.json:
    - HOLDINGS_ID (legacyIdentifier, formerIds[0])
    - BIB_ID (instanceId)
    - LOCATION (permanentLocationId)
    - CALL_NUMBER (callNumber)
    - NOTE (notes[0].note) - optional
    """
    # Column names matching default mapping
    fieldnames = ['HOLDINGS_ID', 'BIB_ID', 'LOCATION', 'CALL_NUMBER', 'NOTE']

    # Ensure output directory exists
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter='\t')
        writer.writeheader()

        # Deduplicate by bib_id + location + call_number
        seen = {}
        for data in records_data:
            key = (data['bib_id'], data['location'], data['full_call_number'])
            if key not in seen:
                holdings_id = generate_holdings_id(data['bib_id'], data['location'], data['full_call_number'])
                seen[key] = holdings_id
                writer.writerow({
                    'HOLDINGS_ID': holdings_id,
                    'BIB_ID': data['bib_id'],
                    'LOCATION': data['location'],
                    'CALL_NUMBER': data['full_call_number'],
                    'NOTE': '',  # No note from 095
                })

    print(f"Holdings: {len(seen)} unique records -> {output_file}")
    return seen  # Return mapping for items to reference


def write_items_tsv(records_data, holdings_map, output_file):
    """
    Write items TSV file with standard column names.

    Columns match default item_mapping.json:
    - ITEM_ID (legacyIdentifier, formerIds[0])
    - BIB_ID (formerIds[1])
    - HOLDINGS_ID (holdingsRecordId)
    - BARCODE (barcode)
    - LOCATION (permanentLocationId)
    - MATERIAL_TYPE (materialTypeId)
    - LOAN_TYPE (permanentLoanTypeId) - optional, uses defaultLoanTypeName
    - CALL_NUMBER (itemLevelCallNumber)
    - COPY_NUMBER (copyNumber)
    - YEAR (yearCaption[0])
    - STATUS (status.name)
    - NOTE (notes[0].note)
    """
    # Column names matching default mapping
    fieldnames = [
        'ITEM_ID', 'BIB_ID', 'HOLDINGS_ID', 'BARCODE', 'LOCATION',
        'MATERIAL_TYPE', 'LOAN_TYPE', 'CALL_NUMBER', 'COPY_NUMBER',
        'YEAR', 'STATUS', 'NOTE'
    ]

    # Ensure output directory exists
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter='\t')
        writer.writeheader()

        for data in records_data:
            # Find the holdings_id for this item
            key = (data['bib_id'], data['location'], data['full_call_number'])
            holdings_id = holdings_map.get(key, '')

            writer.writerow({
                'ITEM_ID': data['item_id'],
                'BIB_ID': data['bib_id'],
                'HOLDINGS_ID': holdings_id,
                'BARCODE': data['barcode'],
                'LOCATION': data['location'],
                'MATERIAL_TYPE': data['material_type'],
                'LOAN_TYPE': '',  # Will use defaultLoanTypeName
                'CALL_NUMBER': data['full_call_number'],
                'COPY_NUMBER': '',
                'YEAR': data['year'],
                'STATUS': 'Available',  # Default status
                'NOTE': '',
            })

    print(f"Items: {len(records_data)} records -> {output_file}")


def show_sample(records_data, count=3):
    """Show sample records for verification."""
    print(f"\n{'='*60}")
    print(f"Sample data (first {count} records)")
    print('='*60)

    for i, data in enumerate(records_data[:count]):
        print(f"\nRecord {i+1}:")
        print(f"  BIB ID: {data['bib_id']}")
        print(f"  Location: {data['location']}")
        print(f"  Barcode: {data['barcode']}")
        print(f"  Call Number: {data['full_call_number']}")
        print(f"  Material Type: {data['material_type']}")
        print(f"  Year: {data['year']}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    marc_file = sys.argv[1]

    # Determine output paths
    if len(sys.argv) >= 3:
        holdings_output = sys.argv[2]
    else:
        base_dir = Path(marc_file).parent.parent  # Go up from instances/
        holdings_output = base_dir / 'holdings' / 'holdings.tsv'

    if len(sys.argv) >= 4:
        items_output = sys.argv[3]
    else:
        base_dir = Path(marc_file).parent.parent
        items_output = base_dir / 'items' / 'items.tsv'

    # Extract data
    records_data = extract_095_data(marc_file)

    if not records_data:
        print("\nNo 095 fields found in the MARC file.")
        sys.exit(0)

    # Show sample
    show_sample(records_data)

    # Write output files
    print(f"\n{'='*60}")
    print("Writing output files (standard column names)")
    print('='*60)

    holdings_map = write_holdings_tsv(records_data, holdings_output)
    write_items_tsv(records_data, holdings_map, items_output)

    print("\n" + "="*60)
    print("Output files are compatible with default mapping templates:")
    print("  - holdingsrecord_mapping.json")
    print("  - item_mapping.json")
    print("="*60)
    print("\nDone!")


if __name__ == '__main__':
    main()
