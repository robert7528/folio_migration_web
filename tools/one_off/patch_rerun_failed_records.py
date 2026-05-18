#!/usr/bin/env python3
"""Add "rerun_failed_records": false to every BatchPoster task in a
folio_migration_tools migration_config.json.

Why: folio_migration_tools BatchPoster defaults rerun_failed_records=True
(batch_poster.py). When a post hits mass HTTP 422 (e.g. re-posting a
dataset already loaded — deterministic UUID collisions), it re-posts every
failed record one-by-one at batch_size=1. For a ~38k-record dataset that is
hours of pointless serial 422s, and the resulting multi-MB log freezes the
web UI log panel. config_service.py never sets this key, so the harmful
default applies to every generated post task.

This script patches an EXISTING migration_config.json in place (the durable
fix lives in config_service.generate_combined_config so regeneration keeps
it). Safe & idempotent: only BatchPoster tasks, only if the key is absent,
backs up first, prints a diff, changes nothing else.

Usage:
    python patch_rerun_failed_records.py /path/to/migration_config.json
    python patch_rerun_failed_records.py /path/to/migration_config.json --dry-run
"""
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    dry_run = "--dry-run" in argv
    if not args:
        print(__doc__)
        return 1

    cfg_path = Path(args[0])
    if not cfg_path.is_file():
        print(f"ERROR: not found: {cfg_path}")
        return 1

    original_text = cfg_path.read_text(encoding="utf-8")
    config = json.loads(original_text)

    tasks = config.get("migrationTasks", [])
    changed = []
    already = []
    for task in tasks:
        if task.get("migrationTaskType") != "BatchPoster":
            continue
        name = task.get("name", "<unnamed>")
        if "rerun_failed_records" in task:
            already.append(f"{name} (={task['rerun_failed_records']}, left as-is)")
            continue
        task["rerun_failed_records"] = False
        changed.append(name)

    # match config_service.generate_combined_config serialization exactly
    # (json.dumps indent=4, ensure_ascii=False, no trailing newline) so the
    # only delta is the inserted keys
    new_text = json.dumps(config, indent=4, ensure_ascii=False)

    print(f"config: {cfg_path}")
    print(f"BatchPoster tasks patched ({len(changed)}): "
          f"{', '.join(changed) if changed else '(none)'}")
    if already:
        print(f"BatchPoster tasks already had the key ({len(already)}): "
              f"{', '.join(already)}")

    if not changed:
        print("Nothing to change. (idempotent — safe to re-run)")
        return 0

    # minimal diff preview (only the inserted lines)
    print("\n--- diff (added lines only) ---")
    old_lines = original_text.splitlines()
    new_lines = new_text.splitlines()
    import difflib
    for d in difflib.unified_diff(old_lines, new_lines, lineterm="", n=2):
        if d.startswith(("+++", "---", "@@")) or d.startswith(("+", "-")):
            print(d)

    if dry_run:
        print("\n[--dry-run] no file written.")
        return 0

    backup = cfg_path.with_name(
        cfg_path.name + ".bak." + datetime.now().strftime("%Y%m%d-%H%M%S")
    )
    shutil.copy2(cfg_path, backup)
    cfg_path.write_text(new_text, encoding="utf-8")
    print(f"\nBackup: {backup}")
    print(f"Wrote:  {cfg_path}")
    print("Re-run is safe (idempotent).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
