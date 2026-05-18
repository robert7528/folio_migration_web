#!/usr/bin/env python3
"""Diagnose whether an oversized MARC record's directory is recoverable.

ISO 2709 field tags live ONLY in the directory (not inline in field data).
For oversized (>99999 byte) records the leader length/base-address and the
directory's 5-digit start-position entries overflow. This tool checks how
much of the directory is still parseable so we can decide whether
synthesize can rebuild the bib from REAL tags (directory-based) or must
fall back (the bib-138131 directory was garbage from entry 1).

For the given 0x1D-split segment it prints:
- raw leader, leader-declared length & base address
- recomputed base address (= first 0x1E offset + 1) and implied entry count
- first 30 + last 10 directory entries: tag / len / start_pos and whether
  the field data at (recomputed_base + start_pos) is in-bounds and ends
  with 0x1E (a valid, usable entry)
- count of valid vs broken entries, and the distinct tags among valid ones

Usage:
    python inspect_oversized.py input.iso --segment-index N
"""
import sys
from collections import Counter
from pathlib import Path


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    flag_vals = {}
    i = 0
    while i < len(argv):
        if argv[i] == "--segment-index":
            flag_vals["--segment-index"] = argv[i + 1]
            i += 2
            continue
        i += 1
    if not args or "--segment-index" not in flag_vals:
        print(__doc__)
        return 1

    raw = Path(args[0]).read_bytes()
    seg_idx = int(flag_vals["--segment-index"])

    segments, start = [], 0
    for j, b in enumerate(raw):
        if b == 0x1D:
            segments.append(raw[start : j + 1])
            start = j + 1
    if seg_idx >= len(segments):
        print(f"segment {seg_idx} out of range (only {len(segments)})")
        return 1

    seg = segments[seg_idx]
    print(f"segment {seg_idx}: {len(seg):,} bytes")
    leader = seg[:24]
    print(f"leader (raw 24B): {leader!r}")
    try:
        print(f"  leader-declared length : {leader[0:5].decode('ascii', 'replace')}")
        print(f"  leader-declared basead : {leader[12:17].decode('ascii', 'replace')}")
    except Exception as e:
        print(f"  leader parse error: {e}")

    dir_end = seg.find(b"\x1e", 24)
    if dir_end < 0:
        print("no 0x1E found after byte 24 — cannot locate directory end")
        return 1
    recomputed_base = dir_end + 1
    dir_bytes = seg[24:dir_end]
    n_entries = len(dir_bytes) // 12
    print(f"first 0x1E at offset      : {dir_end}")
    print(f"recomputed base address   : {recomputed_base}")
    print(f"directory bytes           : {len(dir_bytes)}  -> {n_entries} entries "
          f"(if 12B each); remainder {len(dir_bytes) % 12}")

    rec_len = len(seg)
    valid = 0
    broken = 0
    valid_tags = Counter()

    def entry(k):
        e = dir_bytes[k * 12 : k * 12 + 12]
        tag = e[0:3].decode("ascii", "replace")
        try:
            flen = int(e[3:7])
        except ValueError:
            flen = None
        try:
            spos = int(e[7:12])
        except ValueError:
            spos = None
        ok = False
        why = ""
        if flen is None or spos is None:
            why = "non-numeric len/pos"
        else:
            fstart = recomputed_base + spos
            fend = fstart + flen
            if fend > rec_len:
                why = f"out-of-bounds (fend {fend} > {rec_len})"
            elif seg[fend - 1 : fend] != b"\x1e":
                why = "field not 0x1E-terminated"
            else:
                ok = True
        return tag, flen, spos, ok, why

    for k in range(n_entries):
        _, _, _, ok, _ = entry(k)
        if ok:
            valid += 1
            valid_tags[entry(k)[0]] += 1
        else:
            broken += 1

    print(f"\nentries valid (in-bounds + 0x1E-terminated): {valid}")
    print(f"entries broken                              : {broken}")
    print(f"distinct tags among VALID entries           : "
          f"{sorted(valid_tags.keys())}")
    print(f"valid tag counts (top 15)                   : "
          f"{dict(valid_tags.most_common(15))}")

    print("\n--- first 30 directory entries ---")
    for k in range(min(30, n_entries)):
        tag, flen, spos, ok, why = entry(k)
        flag = "OK " if ok else "BAD"
        print(f"  [{k:3}] tag={tag!r} len={flen} pos={spos} {flag} {why}")

    print("\n--- last 10 directory entries ---")
    for k in range(max(0, n_entries - 10), n_entries):
        tag, flen, spos, ok, why = entry(k)
        flag = "OK " if ok else "BAD"
        print(f"  [{k:3}] tag={tag!r} len={flen} pos={spos} {flag} {why}")

    # show the actual content of the first few VALID non-095 fields
    print("\n--- first 12 VALID non-095 field contents (tag: data[:80]) ---")
    shown = 0
    for k in range(n_entries):
        tag, flen, spos, ok, why = entry(k)
        if not ok or tag == "095":
            continue
        fstart = recomputed_base + spos
        data = seg[fstart : fstart + flen - 1]  # drop trailing 0x1E
        txt = data.decode("utf-8", "replace")
        print(f"  {tag}: {txt[:80]!r}")
        shown += 1
        if shown >= 12:
            break

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
