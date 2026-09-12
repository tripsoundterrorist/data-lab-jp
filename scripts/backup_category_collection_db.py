"""Create an atomic, validated backup of the isolated category database."""

from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import uuid

import category_collection_health as health


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "category-collection.db"
DESTINATION = ROOT / "data" / "backups" / "category-daily"
RETENTION_COUNT = 7
MIN_FREE_BYTES = 256 * 1024 * 1024


def _name() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"category-collection-{stamp}-{uuid.uuid4().hex[:12]}.db"


def _files(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return [
        path for path in directory.glob("category-collection-*.db")
        if path.is_file() and not path.is_symlink()
    ]


def run(source: Path, destination: Path, *, dry_run: bool = False) -> int:
    temporary: Path | None = None
    try:
        if source.is_symlink() or destination.is_symlink() or not source.is_file():
            raise ValueError("UNSAFE_OR_MISSING_PATH")
        source_result = health.assess(source)
        if source_result.status != health.HEALTHY:
            raise ValueError("SOURCE_HEALTH_FAILED")
        probe = destination
        while not probe.exists():
            if probe.parent == probe:
                raise ValueError("DESTINATION_UNAVAILABLE")
            probe = probe.parent
        required = max(MIN_FREE_BYTES, source.stat().st_size * 3)
        if not probe.is_dir() or shutil.disk_usage(probe).free < required:
            raise ValueError("DISK_SPACE_INSUFFICIENT")
        if dry_run:
            print(
                f"backup_status=ready dry_run=true source_items={source_result.item_count} "
                f"source_snapshots={source_result.snapshot_count} backup_created=false"
            )
            return 0

        destination.mkdir(parents=True, exist_ok=True)
        final = destination / _name()
        temporary = destination / f".tmp-{uuid.uuid4().hex}.db"
        source_uri = f"file:{source.resolve().as_posix()}?mode=ro"
        with closing(sqlite3.connect(source_uri, uri=True)) as source_connection:
            with closing(sqlite3.connect(temporary)) as destination_connection:
                source_connection.backup(destination_connection, pages=256, sleep=0.05)
        backup_result = health.assess(temporary)
        if (
            backup_result.status != health.HEALTHY
            or backup_result.source_count != source_result.source_count
            or backup_result.item_count != source_result.item_count
            or backup_result.snapshot_count != source_result.snapshot_count
            or backup_result.successful_run_count != source_result.successful_run_count
        ):
            raise ValueError("BACKUP_VALIDATION_FAILED")
        os.replace(temporary, final)
        temporary = None
        candidates = sorted(
            _files(destination), key=lambda path: (path.stat().st_mtime_ns, path.name),
            reverse=True,
        )
        for old in candidates[RETENTION_COUNT:]:
            old.unlink()
        print(
            f"backup_status=success source_items={source_result.item_count} "
            f"source_snapshots={source_result.snapshot_count} retained_backups={len(_files(destination))}"
        )
        return 0
    except Exception:
        print("backup_status=failed error_code=CATEGORY_BACKUP_FAILED", file=sys.stderr)
        return 2
    finally:
        if temporary is not None and temporary.exists():
            try:
                temporary.unlink()
            except OSError:
                pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Back up isolated category collection data")
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--destination", type=Path, default=DESTINATION)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    return run(args.source, args.destination, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
