"""Run one explicitly approved 300-item collection against a disposable DB."""

from __future__ import annotations

import argparse
from contextlib import closing, redirect_stderr, redirect_stdout
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from typing import Any

import revenue_mvp_expansion_page_validator as page_validator
import revenue_mvp_public_expansion_coverage as coverage


ROOT = Path(__file__).resolve().parents[1]
COLLECTOR = ROOT / "scripts" / "collect-dmm-items.py"
VERSION = "0.1"
VERIFIED = "ISOLATED_COLLECTION_VERIFIED"
BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class IsolatedCollectionReceipt:
    version: str
    status: str
    source_sha256: str | None
    source_identity_preserved: bool
    api_calls: int
    pages_fetched: int
    processed_items: int
    duplicate_content_ids: int
    page_validation_status: str | None
    base_eligible_count: int
    fresh_base_eligible_count: int
    target_gap: int
    temporary_database_retained: bool
    production_database_write_performed: bool
    publication_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _blocked(reason: str, source_sha256: str | None = None) -> IsolatedCollectionReceipt:
    return IsolatedCollectionReceipt(
        VERSION, BLOCKED, source_sha256, False, 0, 0, 0, 0, None, 0, 0,
        300, False, False, False, (reason,),
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_database(source: Path, destination: Path) -> None:
    with closing(sqlite3.connect(f"{source.resolve().as_uri()}?mode=ro", uri=True)) as src:
        src.execute("PRAGMA query_only = ON")
        if src.execute("PRAGMA integrity_check").fetchone() != ("ok",):
            raise ValueError("SOURCE_INTEGRITY_FAILED")
        if src.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise ValueError("SOURCE_FOREIGN_KEY_FAILED")
        running = src.execute(
            "SELECT count(*) FROM collection_runs WHERE run_type='native' "
            "AND status='running' AND finished_at IS NULL"
        ).fetchone()[0]
        if running:
            raise ValueError("ACTIVE_NATIVE_RUN")
        with closing(sqlite3.connect(destination)) as dst:
            src.backup(dst, pages=256, sleep=0.05)


def _load_collector():
    spec = importlib.util.spec_from_file_location("isolated_collect_dmm_items", COLLECTOR)
    if spec is None or spec.loader is None:
        raise RuntimeError("COLLECTOR_LOAD_FAILED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_collector(database: Path, env_path: Path) -> int:
    module = _load_collector()
    module.DATABASE_PATH = database
    module.ENV_PATH = env_path
    previous = sys.argv
    try:
        sys.argv = [str(COLLECTOR), "--max-items", "300", "--max-pages", "6"]
        # Collector output is intentionally suppressed; only the bounded receipt
        # from this harness is returned to the operator.
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return int(module.main())
    finally:
        sys.argv = previous


def _latest_run(database: Path) -> tuple[sqlite3.Row, tuple[page_validator.PageObservation, ...]]:
    with closing(sqlite3.connect(database)) as connection:
        connection.row_factory = sqlite3.Row
        run = connection.execute(
            "SELECT * FROM collection_runs WHERE run_type='native' "
            "ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        if run is None:
            raise ValueError("RUN_MISSING")
        page_rows = connection.execute(
            """SELECT s.source_offset, s.source_position, i.content_id
               FROM item_snapshots AS s
               JOIN items AS i ON i.id=s.item_id
               WHERE s.collection_run_id=?
               ORDER BY s.source_offset,s.source_position,s.id""",
            (run["collection_run_id"],),
        ).fetchall()
    grouped: dict[int, list[str]] = {}
    for row in page_rows:
        grouped.setdefault(row["source_offset"], []).append(row["content_id"])
    pages = tuple(
        page_validator.PageObservation(offset, 50, len(values), tuple(values))
        for offset, values in sorted(grouped.items())
    )
    return run, pages


def assess(source: Path, env_path: Path, *, evaluated_at: datetime) -> IsolatedCollectionReceipt:
    before_sha: str | None = None
    try:
        if (
            evaluated_at.tzinfo is None or source.is_symlink() or env_path.is_symlink()
            or not source.is_file() or not env_path.is_file()
        ):
            return _blocked("INPUT_INVALID")
        before_sha = _sha256(source)
        with tempfile.TemporaryDirectory(prefix="data-lab-expansion-run-") as directory:
            disposable = Path(directory) / "data-lab.db"
            _copy_database(source, disposable)
            exit_code = _run_collector(disposable, env_path)
            if exit_code != 0:
                return _blocked("ISOLATED_COLLECTOR_FAILED", before_sha)
            run, pages = _latest_run(disposable)
            page_check = page_validator.validate(pages)
            if (
                run["status"] != "success"
                or run["max_items"] != 300
                or run["max_pages"] != 6
                or run["api_calls"] != 6
                or run["pages_fetched"] != 6
                or run["processed_items"] != 300
                or run["snapshots_inserted"] != 300
                or run["duplicate_content_ids_across_pages"] != 0
                or page_check.status != page_validator.PASS
            ):
                return _blocked("ISOLATED_RUN_CONTRACT_FAILED", before_sha)
            # The approval timestamp can precede snapshots created during the
            # bounded run. Evaluate freshness only after collection completes.
            coverage_evaluated_at = max(
                evaluated_at.astimezone(timezone.utc), datetime.now(timezone.utc)
            )
            covered = coverage.assess(disposable, evaluated_at=coverage_evaluated_at)
            if covered.status == coverage.FAIL_CLOSED:
                return _blocked("COVERAGE_AUDIT_FAILED", before_sha)
            receipt = IsolatedCollectionReceipt(
                VERSION, VERIFIED, before_sha, True, run["api_calls"],
                run["pages_fetched"], run["processed_items"],
                run["duplicate_content_ids_across_pages"], page_check.status,
                covered.base_eligible_count, covered.fresh_base_eligible_count,
                covered.target_gap, False, False, False,
                ("DISPOSABLE_DATABASE_ONLY", "EXPLICIT_PUBLICATION_REVIEW_REQUIRED"),
            )
        if _sha256(source) != before_sha:
            return _blocked("SOURCE_IDENTITY_CHANGED", before_sha)
        return receipt
    except (OSError, sqlite3.Error, ValueError, RuntimeError, ImportError):
        return _blocked("ISOLATED_COLLECTION_FAILED", before_sha)


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("timestamp must include an offset")
    return parsed.astimezone(timezone.utc)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-db", required=True, type=Path)
    parser.add_argument("--env-file", required=True, type=Path)
    parser.add_argument("--evaluated-at", required=True, type=_timestamp)
    args = parser.parse_args(argv)
    result = assess(args.source_db, args.env_file, evaluated_at=args.evaluated_at)
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == VERIFIED else 2


if __name__ == "__main__":
    raise SystemExit(main())
