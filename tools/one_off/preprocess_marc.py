#!/usr/bin/env python3
"""Repair a corrupt HyLib MARC ISO export so folio_migration_tools can read it.

Background (THU 2026-05-15, file 202605151142-11802.iso):
  The HyLib export tool writes a wrong record length into the 5-digit leader
  length field whenever a single record exceeds 99999 bytes (the MARC21
  limit). pymarc trusts that length, jumps to the wrong offset for the next
  record, and from then on every record is misframed -- so an 11802-record
  file is read as only 4 records.

  The 0x1D end-of-record markers are intact, so we can re-split on 0x1D and
  recompute each record's leader length. ~99.97% of records are recovered
  this way. The few that can't be:
    - oversized (> 99999 bytes): needs case-by-case split (see
      synthesize_seg3.py for the bib-138131 example)
    - unparseable leader (first bytes not ASCII digits, encoding broken)
    - missing 001 (transform_bibs rejects these for Voyager migrations)

Usage:
    python preprocess_marc.py input.iso [output.iso] [--keep-no-001]

    output.iso defaults to <input_stem>_fixed.iso next to the input.
    A <output_stem>_report.txt is written alongside.

    --keep-no-001   keep records that have no 001 field (default: skip them,
                    because transform_bibs requires 001 for Voyager source).
                    Switch this on if PM decides to use 035 as the legacy id
                    via a mapping-rules change instead.

This script is intentionally a one-off CLI (no service interface). The
reusable parts will be lifted into the web "ISO Health Check" feature later.
"""
import io
import sys
from collections import Counter
from pathlib import Path

try:
    import pymarc
except ImportError:
    sys.exit("ERROR: pymarc not installed. Run: pip install pymarc")

MARC_MAX = 99999          # leader length field is 5 ASCII digits
LEADER_LEN = 24


def split_on_eor(raw: bytes):
    """Split raw bytes into segments, each ending with its 0x1D marker.

    Returns (segments, trailing_len). trailing_len is the number of bytes
    after the last 0x1D (should be 0 for a well-terminated file).
    """
    segments = []
    start = 0
    for i, b in enumerate(raw):
        if b == 0x1D:
            segments.append(raw[start : i + 1])
            start = i + 1
    return segments, len(raw) - start


def fix_leader_length(seg: bytes) -> bytes:
    """Overwrite the first 5 leader bytes with the segment's actual length."""
    return f"{len(seg):05d}".encode("ascii") + seg[5:]


def try_parse(seg: bytes):
    """Parse a single (length-patched) segment. Returns (record, error_str)."""
    patched = fix_leader_length(seg)
    try:
        reader = pymarc.MARCReader(
            io.BytesIO(patched),
            to_unicode=True,
            force_utf8=True,
            permissive=True,
        )
        rec = next(reader)
    except Exception as e:  # noqa: BLE001 - want any failure classified
        return None, f"{type(e).__name__}: {str(e)[:80]}"
    if rec is None:
        err = getattr(reader, "current_exception", None)
        return None, f"{type(err).__name__ if err else 'None'}: {str(err)[:80]}"
    return rec, None


def _raw_ident(seg: bytes):
    """Best-effort identify a segment WITHOUT relying on leader/directory
    (works even when both are corrupt). Returns a short label string.

    The directory still ends at the first 0x1E at/after byte 24; the data
    area follows. 001 is the first control field (no 0x1F). A title hint =
    first data field's first CJK-bearing subfield value.
    """
    de = seg.find(b"\x1e", 24)
    if de < 0 or de + 1 >= len(seg):
        return f"head={seg[:40].hex()}"
    data = seg[de + 1 :]
    if data.endswith(b"\x1d"):
        data = data[:-1]
    bib001 = None
    title = None
    for fb in [f for f in data.split(b"\x1e") if f][:30]:
        if b"\x1f" not in fb:
            t = fb.decode("utf-8", "replace").strip()
            if bib001 is None and 0 < len(t) <= 20 and any(c.isdigit() for c in t):
                bib001 = t
        elif title is None:
            for part in fb.split(b"\x1f")[1:]:
                if not part:
                    continue
                v = part[1:].decode("utf-8", "replace")
                if len(v) >= 4 and any("一" <= ch <= "鿿" for ch in v):
                    title = v[:50]
                    break
    bits = []
    bits.append(f"001~={bib001}" if bib001 else "001=?")
    if title:
        bits.append(f"title~={title}")
    if not bib001 and not title:
        bits.append(f"head={seg[:40].hex()}")
    return "  ".join(bits)


def _rec_ident(rec) -> str:
    """Identify a parsed record that lacks 001, via 035 / 020 / 245."""
    bits = []
    for tag in ("035", "020", "245"):
        fs = rec.get_fields(tag)
        if fs:
            bits.append(f"{tag}={fs[0].value()[:60]}")
    return "  ".join(bits) if bits else "(no 035/020/245 either)"


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    flags = {a for a in argv if a.startswith("--")}
    if not args:
        print(__doc__)
        return 1

    keep_no_001 = "--keep-no-001" in flags
    in_path = Path(args[0])
    out_path = Path(args[1]) if len(args) > 1 else in_path.with_name(
        in_path.stem + "_fixed.iso"
    )
    report_path = out_path.with_name(out_path.stem + "_report.txt")

    raw = in_path.read_bytes()
    segments, trailing = split_on_eor(raw)

    kept = bytearray()
    stats = Counter()
    skipped = {
        "too_short": [],
        "oversized": [],
        "unparseable": [],
        "no_001": [],
    }

    for idx, seg in enumerate(segments):
        if len(seg) < LEADER_LEN + 2:  # leader + at least 0x1E + 0x1D
            skipped["too_short"].append(idx)
            stats["too_short"] += 1
            continue
        if len(seg) > MARC_MAX:
            skipped["oversized"].append((idx, len(seg), _raw_ident(seg)))
            stats["oversized"] += 1
            continue
        rec, err = try_parse(seg)
        if rec is None:
            skipped["unparseable"].append((idx, err, _raw_ident(seg)))
            stats["unparseable"] += 1
            continue
        if not rec.get_fields("001") and not keep_no_001:
            skipped["no_001"].append((idx, _rec_ident(rec)))
            stats["no_001"] += 1
            continue
        kept += fix_leader_length(seg)
        stats["ok"] += 1

    out_path.write_bytes(bytes(kept))

    # ---- report ----
    lines = []
    lines.append(f"preprocess_marc.py report")
    lines.append(f"input:  {in_path}  ({len(raw):,} bytes)")
    lines.append(f"output: {out_path}  ({len(kept):,} bytes)")
    lines.append(f"keep_no_001: {keep_no_001}")
    lines.append("")
    lines.append(f"segments found (split on 0x1D): {len(segments):,}")
    if trailing:
        lines.append(f"WARNING: {trailing} trailing bytes after last 0x1D (ignored)")
    lines.append("")
    lines.append(f"  written OK:    {stats['ok']:,}")
    lines.append(f"  too_short:     {stats['too_short']:,}")
    lines.append(f"  oversized:     {stats['oversized']:,}  (>{MARC_MAX} bytes)")
    lines.append(f"  unparseable:   {stats['unparseable']:,}")
    lines.append(f"  no_001:        {stats['no_001']:,}")
    lines.append("")
    if skipped["oversized"]:
        lines.append("OVERSIZED (need case-by-case split, e.g. synthesize_seg3.py):")
        for idx, sz, ident in skipped["oversized"]:
            lines.append(f"  seg {idx}: {sz:,} bytes  |  {ident}")
    if skipped["unparseable"]:
        lines.append("UNPARSEABLE (leader/encoding broken; usually unsalvageable):")
        for idx, err, ident in skipped["unparseable"]:
            lines.append(f"  seg {idx}: {err}")
            lines.append(f"           {ident}")
    if skipped["no_001"]:
        lines.append("NO 001 (skipped; rerun with --keep-no-001 if using 035 fallback):")
        for idx, ident in skipped["no_001"]:
            lines.append(f"  seg {idx}:  {ident}")
    if skipped["too_short"]:
        lines.append("TOO_SHORT (empty / truncated tail segments):")
        lines.append("  " + ", ".join(f"seg {i}" for i in skipped["too_short"]))

    report = "\n".join(lines) + "\n"
    report_path.write_text(report, encoding="utf-8")
    print(report)
    print(f"Wrote {out_path}")
    print(f"Wrote {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
