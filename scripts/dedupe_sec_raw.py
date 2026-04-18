"""
scripts/dedupe_sec_raw.py

One-shot cleanup for accumulated `company_facts_<CIK>_*.json` duplicates in
data/raw/sec/. Groups files by CIK, SHA-256's each payload, keeps only the
most-recent file per unique hash, and deletes the rest.

Run:
    python scripts/dedupe_sec_raw.py          # dry-run (default)
    python scripts/dedupe_sec_raw.py --apply  # actually delete

Why this exists: before the content-hash short-circuit landed in
core/sec_client.py, the ingest loop re-downloaded identical SEC payloads every
cadence tick. AAPL alone had ~21 MB of duplicate copies on disk.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

# Make `core.*` importable when running this file directly.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.settings import settings  # noqa: E402


def content_hash(path: Path) -> str:
    with open(path) as f:
        data = json.load(f)
    canonical = json.dumps(data, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="Actually delete duplicates (default: dry-run)."
    )
    args = parser.parse_args()

    sec_dir = Path(settings.RAW_DATA_DIR) / "sec"
    if not sec_dir.exists():
        print(f"[dedupe] No SEC raw directory at {sec_dir}; nothing to do.")
        return 0

    by_cik: dict[str, list[Path]] = defaultdict(list)
    for path in sec_dir.glob("company_facts_*.json"):
        parts = path.stem.split("_")
        if len(parts) >= 3:
            by_cik[parts[2]].append(path)

    total_removed = 0
    bytes_reclaimed = 0

    for cik, paths in sorted(by_cik.items()):
        if len(paths) <= 1:
            continue

        paths.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        seen_hashes: dict[str, Path] = {}
        duplicates: list[Path] = []

        for path in paths:
            try:
                h = content_hash(path)
            except Exception as e:
                print(f"[dedupe] Skipping unreadable {path.name}: {e}")
                continue
            if h in seen_hashes:
                duplicates.append(path)
            else:
                seen_hashes[h] = path

        if not duplicates:
            print(f"[dedupe] CIK {cik}: {len(paths)} files, all unique — keeping all.")
            continue

        kept = seen_hashes.values()
        print(
            f"[dedupe] CIK {cik}: {len(paths)} files → {len(kept)} unique. "
            f"Removing {len(duplicates)} duplicate(s)."
        )
        for dup in duplicates:
            size = dup.stat().st_size
            bytes_reclaimed += size
            total_removed += 1
            if args.apply:
                dup.unlink()
                print(f"    deleted {dup.name} ({size / 1_000_000:.1f} MB)")
            else:
                print(f"    would delete {dup.name} ({size / 1_000_000:.1f} MB)")

    mode = "deleted" if args.apply else "would delete"
    print(
        f"\n[dedupe] {mode} {total_removed} file(s), "
        f"{bytes_reclaimed / 1_000_000:.1f} MB reclaimable."
    )
    if not args.apply and total_removed:
        print("[dedupe] Re-run with --apply to actually remove them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
