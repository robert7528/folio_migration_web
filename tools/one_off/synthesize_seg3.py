#!/usr/bin/env python3
"""Split one oversized HyLib MARC record into a clean bib + holdings/items TSV.

Background (THU 2026-05-15, bib 138131 = 俗文學叢刊):
  The HyLib export packed a 600-item multi-volume serial into a single MARC
  record (189,378 bytes), exceeding the MARC21 99999-byte leader limit. Its
  leader length AND base address overflowed, so the directory is unreadable.
  preprocess_marc.py can't fix it (can't shrink below the limit), so this
  case-by-case tool:

    1. Walks the record's data area directly (split on 0x1E), bypassing the
       corrupt directory.
    2. Rebuilds a clean, standards-valid MARC bib record (metadata only, no
       095) small enough to fit the limit.  ->  <client>_<bibid>_bib.mrc
    3. Extracts the 600 095 item fields into holdings.tsv + items.tsv using
       the SAME logic as tools/extract_095_standard.py so they merge cleanly.
       ->  <client>_<bibid>_holdings.tsv  /  <client>_<bibid>_items.tsv

  PM then: cat the .mrc into the main ISO, and append the TSV rows (minus
  header) to the holdings/items TSVs produced by extract_095_standard.py.

Per the agreed product direction this stays a hand-tooled one-off: the bib
field-tag order is hardcoded (the directory is corrupt so tags can't be read
from it). It is specific to the THU bib-138131 record shape; eyeball the
printed verification dump before trusting the output for any other record.

Usage:
    python synthesize_seg3.py input.iso [--client thu] [--segment-index N]
                              [--out-dir DIR] [--no-typo-patch]

    --segment-index N   process this 0x1D-split segment (default: first
                        segment exceeding 99999 bytes)
    --out-dir DIR       where to write the 3 output files (default: input dir)
    --no-typo-patch     do NOT fix the v.132 year typo (default: fix it)
"""
import io
import re
import sys
from collections import Counter
from pathlib import Path

try:
    import pymarc
    from pymarc import Field, Record, Subfield
except ImportError:
    sys.exit("ERROR: pymarc not installed. Run: pip install pymarc")

MARC_MAX = 99999

# --- v.132 year typo (HyLib source error) -------------------------------
# barcode C552588 / volume v.132: $y and $z both read '20002'; the volumes
# immediately before (v.131) and after (v.133) are '2002', and the catalog
# timestamps are the same 2012-02-22 batch -- a single stray extra '0'.
# PM expects the source to be fixed too, but we patch locally as a backstop.
TYPO_BARCODE = "C552588"
TYPO_BAD = "20002"
TYPO_GOOD = "2002"

# --- bib field tag order ------------------------------------------------
# The directory is corrupt so tags can't be read from it. This is the
# observed field order for THU bib 138131 (see docs / inspect_marc3 dump).
# Field index 18 ($d $e $p $y, a THU "default holdings" stray line with no
# $a/$b/$t) and anything past TAG_ORDER before the 095 block is dropped.
TAG_ORDER = [
    "001",  # control number (legacy bib id)
    "005",  # latest transaction datetime
    "008",  # fixed-length data elements
    "015",  # national bibliography number
    "020",  # ISBN (whole set)
    "020",  # ISBN (2nd series)
    "020",  # ISBN (3rd series)
    "035",  # system control number
    "040",  # cataloging source
    "041",  # language code
    "084",  # other classification number
    "245",  # title statement
    "250",  # edition statement
    "260",  # publication
    "300",  # physical description
    "505",  # formatted contents note
    "650",  # subject - topical
    "710",  # added entry - corporate name
]
CONTROL_TAGS = {"001", "005", "008"}

# Synthesized leader. 24 chars exactly. pos9='a' (UTF-8). Record type 'a'
# (language material), bib level 'm' (monograph) -- the source leader was
# corrupt so these are clean defaults; a cataloger can refine later.
SYNTH_LEADER = "00000nam a2200000 a 4500"


# === item / holdings logic -- KEEP IN SYNC WITH tools/extract_095_standard.py ===
def normalize_whitespace(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def generate_holdings_id(bib_id, location, material_type, call_number):
    combined = f"{bib_id}-{location}-{material_type}_{call_number}"
    return combined.replace(" ", "_").replace("/", "-")


HOLDINGS_COLS = ["HOLDINGS_ID", "BIB_ID", "LOCATION", "CALL_NUMBER",
                 "CALL_NUMBER_TYPE", "NOTE"]
ITEM_COLS = ["ITEM_ID", "BIB_ID", "HOLDINGS_ID", "BARCODE", "LOCATION",
             "MATERIAL_TYPE", "LOAN_TYPE", "CALL_NUMBER", "COPY_NUMBER",
             "YEAR", "STATUS", "NOTE"]
# === end sync block =====================================================


def split_on_eor(raw: bytes):
    segments, start = [], 0
    for i, b in enumerate(raw):
        if b == 0x1D:
            segments.append(raw[start : i + 1])
            start = i + 1
    return segments


def decode(b: bytes) -> str:
    return b.decode("utf-8", errors="replace")


def parse_subfields(fb: bytes):
    """Return list of (code, value). fb is field bytes WITHOUT indicators."""
    out = []
    for part in fb.split(b"\x1f")[1:]:
        if not part:
            continue
        out.append((chr(part[0]), decode(part[1:])))
    return out


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    flag_vals = {}
    flags = set()
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--client", "--segment-index", "--out-dir"):
            flag_vals[a] = argv[i + 1]
            i += 2
            continue
        if a.startswith("--"):
            flags.add(a)
        i += 1

    if not args:
        print(__doc__)
        return 1

    in_path = Path(args[0])
    client = flag_vals.get("--client", "thu")
    out_dir = Path(flag_vals.get("--out-dir", str(in_path.parent)))
    patch_typo = "--no-typo-patch" not in flags

    raw = in_path.read_bytes()
    segments = split_on_eor(raw)

    if "--segment-index" in flag_vals:
        seg_idx = int(flag_vals["--segment-index"])
    else:
        seg_idx = next(
            (i for i, s in enumerate(segments) if len(s) > MARC_MAX), -1
        )
        if seg_idx < 0:
            print("No segment exceeds 99999 bytes; nothing to do.")
            return 0

    seg = segments[seg_idx]
    print(f"Processing segment {seg_idx}: {len(seg):,} bytes")

    # data area starts after the first 0x1E (end of corrupt directory),
    # ends before the trailing 0x1D
    dir_end = seg.find(b"\x1e", 24)
    data_area = seg[dir_end + 1 : -1]
    fields_raw = [f for f in data_area.split(b"\x1e") if f]

    bib_raw = []
    items_subs = []
    seen_item = False
    dropped = []
    for fb in fields_raw:
        codes = {c for c, _ in parse_subfields(fb)} if b"\x1f" in fb else set()
        is_095 = {"a", "b", "p", "t"} <= codes
        if is_095:
            seen_item = True
            items_subs.append(dict(parse_subfields(fb)))
        elif seen_item:
            dropped.append(("after-items", fb[:60]))
        else:
            bib_raw.append(fb)

    if len(bib_raw) > len(TAG_ORDER):
        for fb in bib_raw[len(TAG_ORDER):]:
            dropped.append(("beyond-tag-order", fb[:60]))
        bib_raw = bib_raw[: len(TAG_ORDER)]
    if len(bib_raw) != len(TAG_ORDER):
        print(f"WARNING: expected {len(TAG_ORDER)} bib fields, got "
              f"{len(bib_raw)} -- tag mapping may be off. Verify the dump.")

    # --- build clean bib record ---
    rec = Record()
    rec.leader = SYNTH_LEADER
    bib_id = None
    for tag, fb in zip(TAG_ORDER, bib_raw):
        if tag in CONTROL_TAGS:
            val = decode(fb)
            if tag == "001":
                bib_id = val.strip()
            rec.add_field(Field(tag=tag, data=val))
        else:
            ind = [
                chr(c) if 32 <= c < 127 else " " for c in (fb[:2] + b"  ")[:2]
            ]
            subs = [Subfield(code=c, value=v) for c, v in parse_subfields(fb[2:])]
            if not subs:
                continue
            rec.add_field(Field(tag=tag, indicators=ind, subfields=subs))

    if not bib_id:
        print("ERROR: could not extract 001/bib id from segment.")
        return 2

    bib_bytes = rec.as_marc()
    if len(bib_bytes) > MARC_MAX:
        print(f"ERROR: synthesized bib is {len(bib_bytes)} bytes (>99999). "
              f"Should not happen without 095 -- aborting.")
        return 2

    out_dir.mkdir(parents=True, exist_ok=True)
    bib_path = out_dir / f"{client}_{bib_id}_bib.mrc"
    bib_path.write_bytes(bib_bytes)

    # --- items / holdings (mirror extract_095_standard.py) ---
    records_data = []
    typo_hits = 0
    for subs in items_subs:
        d = {
            "bib_id": bib_id,
            "library": normalize_whitespace(subs.get("a", "")),
            "location": normalize_whitespace(subs.get("b", "")),
            "barcode": normalize_whitespace(subs.get("c", "")),
            "classification": normalize_whitespace(subs.get("d", "")),
            "cutter": normalize_whitespace(subs.get("e", "")),
            "material_type": normalize_whitespace(subs.get("p", "")),
            "price": normalize_whitespace(subs.get("r", "")),
            "date": normalize_whitespace(subs.get("s", "")),
            "call_number_type": normalize_whitespace(subs.get("t", "")),
            "year": normalize_whitespace(subs.get("y", "")),
            "full_call_number": normalize_whitespace(subs.get("z", "")),
        }
        if patch_typo and d["barcode"] == TYPO_BARCODE:
            if d["year"] == TYPO_BAD:
                d["year"] = TYPO_GOOD
                typo_hits += 1
            d["full_call_number"] = d["full_call_number"].replace(
                TYPO_BAD, TYPO_GOOD
            )
        # call number: prefer $d (+ $e + $y); else strip mat-type prefix off $z
        if d["classification"]:
            parts = [d["classification"]]
            if d["cutter"]:
                parts.append(d["cutter"])
            if d["year"]:
                parts.append(d["year"])
            d["full_call_number"] = " ".join(parts)
        elif d["full_call_number"] and d["material_type"]:
            prefix = d["material_type"] + " "
            if d["full_call_number"].startswith(prefix):
                d["full_call_number"] = d["full_call_number"][len(prefix):]
        d["item_id"] = d["barcode"] if d["barcode"] else f"ITEM-{len(records_data)+1:08d}"
        records_data.append(d)

    # holdings: dedup by (bib, location, material_type, full_call_number)
    holdings_map = {}
    holdings_rows = []
    for d in records_data:
        key = (d["bib_id"], d["location"], d["material_type"],
               d["full_call_number"])
        if key not in holdings_map:
            hid = generate_holdings_id(*key)
            holdings_map[key] = hid
            holdings_rows.append({
                "HOLDINGS_ID": hid,
                "BIB_ID": d["bib_id"],
                "LOCATION": d["location"],
                "CALL_NUMBER": d["full_call_number"],
                "CALL_NUMBER_TYPE": d["call_number_type"],
                "NOTE": "",
            })

    item_rows = []
    for d in records_data:
        key = (d["bib_id"], d["location"], d["material_type"],
               d["full_call_number"])
        item_rows.append({
            "ITEM_ID": d["item_id"],
            "BIB_ID": d["bib_id"],
            "HOLDINGS_ID": holdings_map[key],
            "BARCODE": d["barcode"],
            "LOCATION": d["location"],
            "MATERIAL_TYPE": d["material_type"],
            "LOAN_TYPE": "",
            "CALL_NUMBER": d["full_call_number"],
            "COPY_NUMBER": "",
            "YEAR": d["year"],
            "STATUS": "Available",
            "NOTE": "",
        })

    def write_tsv(path, cols, rows):
        with path.open("w", encoding="utf-8", newline="") as fh:
            fh.write("\t".join(cols) + "\n")
            for r in rows:
                fh.write("\t".join(
                    str(r[c]).replace("\t", " ").replace("\n", " ")
                    for c in cols
                ) + "\n")

    hold_path = out_dir / f"{client}_{bib_id}_holdings.tsv"
    item_path = out_dir / f"{client}_{bib_id}_items.tsv"
    write_tsv(hold_path, HOLDINGS_COLS, holdings_rows)
    write_tsv(item_path, ITEM_COLS, item_rows)

    # --- verification dump ---
    print("\n" + "=" * 60)
    print("SYNTHESIZED BIB (round-trip via pymarc)")
    print("=" * 60)
    rr = next(pymarc.MARCReader(io.BytesIO(bib_bytes), to_unicode=True,
                                force_utf8=True, permissive=True))
    print(f"  leader: {rr.leader}")
    for f in rr.get_fields():
        print(f"  {f.tag}: {f.value()[:90]}")

    print("\n" + "=" * 60)
    print("ITEMS / HOLDINGS")
    print("=" * 60)
    print(f"  items:    {len(item_rows)}")
    print(f"  holdings: {len(holdings_rows)} (dedup by bib+loc+mat+callno)")
    loc_counts = Counter(r["LOCATION"] for r in item_rows)
    print(f"  by location: {dict(loc_counts)}")
    print(f"  typo patch applied: {patch_typo}  (v.132 $y fixes: {typo_hits})")
    print("\n  holdings rows:")
    for r in holdings_rows:
        print(f"    {r['HOLDINGS_ID']}  ->  {r['CALL_NUMBER']}")
    print("\n  sample items (first 3):")
    for r in item_rows[:3]:
        print(f"    {r['ITEM_ID']} | {r['LOCATION']} | {r['CALL_NUMBER']} "
              f"| {r['YEAR']} | hold={r['HOLDINGS_ID']}")
    if dropped:
        print(f"\n  dropped {len(dropped)} non-bib/non-095 field(s):")
        for why, preview in dropped:
            print(f"    [{why}] {preview}")

    print("\n" + "=" * 60)
    print(f"Wrote {bib_path}  ({len(bib_bytes):,} bytes)")
    print(f"Wrote {hold_path}  ({len(holdings_rows)} rows)")
    print(f"Wrote {item_path}  ({len(item_rows)} rows)")
    print("\nNext (on Linux): cat the .mrc into the fixed ISO, then append")
    print("the TSV rows (skip header) to the main holdings/items TSVs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
