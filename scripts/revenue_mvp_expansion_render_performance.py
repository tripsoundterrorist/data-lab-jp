"""Offline, aggregate-only render performance verification for 300 items."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from time import perf_counter_ns
from typing import Any

import revenue_mvp_unordered_publication_candidate as renderer
import revenue_mvp_unordered_surface_review as contract


VERSION = "0.1"
VERIFIED = "CANDIDATE_RENDER_PERFORMANCE_VERIFIED"
BLOCKED = "BLOCKED"
TARGET_COUNT = 300
REPETITIONS = 5
MAX_RENDER_MILLISECONDS = 2_000
MAX_ARTIFACT_BYTES = 2_000_000


@dataclass(frozen=True)
class RenderPerformanceReceipt:
    version: str
    status: str
    candidate_item_count: int
    repetitions: int
    maximum_render_milliseconds: float | None
    artifact_bytes: int | None
    deterministic_output: bool
    rendered_structure_verified: bool
    source_database_sha256: str | None
    artifact_sha256: str | None
    candidate_identifiers_exposed: bool
    output_written: bool
    publication_allowed: bool
    production_write_allowed: bool
    deployment_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _blocked(*reasons: str) -> RenderPerformanceReceipt:
    return RenderPerformanceReceipt(
        VERSION, BLOCKED, 0, REPETITIONS, None, None, False, False,
        None, None, False, False, False, False, False,
        tuple(sorted(set(reasons))),
    )


def verify(database: Path, *, expected_database_sha256: str) -> RenderPerformanceReceipt:
    connection: sqlite3.Connection | None = None
    try:
        if (
            database.is_symlink() or not database.is_file()
            or len(expected_database_sha256) != 64
            or any(character not in "0123456789abcdef" for character in expected_database_sha256)
        ):
            return _blocked("INPUT_BOUNDARY_INVALID")
        before = _digest(database)
        if before != expected_database_sha256:
            return _blocked("DATABASE_IDENTITY_MISMATCH")
        connection = sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        run = connection.execute(
            "SELECT * FROM collection_runs WHERE run_type='native' "
            "ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        if run is None or any((
            run["status"] != "success", run["max_items"] != TARGET_COUNT,
            run["max_pages"] != 6, run["api_calls"] != 6,
            run["pages_fetched"] != 6, run["processed_items"] != TARGET_COUNT,
            run["snapshots_inserted"] != TARGET_COUNT,
            run["duplicate_content_ids_across_pages"] != 0,
        )):
            return _blocked("LATEST_RUN_CONTRACT_INVALID")
        rows = connection.execute(
            """SELECT t.title,s.price_min,s.observed_at
               FROM item_snapshots s
               JOIN item_snapshot_titles t ON t.snapshot_id=s.id
               WHERE s.collection_run_id=?
               ORDER BY s.source_offset,s.source_position,s.id""",
            (run["collection_run_id"],),
        ).fetchall()
        if len(rows) != TARGET_COUNT:
            return _blocked("EXACT_CANDIDATE_COUNT_INVALID")
        observed = [datetime.fromisoformat(row["observed_at"].replace("Z", "+00:00")) for row in rows]
        evaluated_at = max(observed).astimezone(timezone.utc)
        as_of = evaluated_at.isoformat().replace("+00:00", "Z")
        items: list[dict[str, Any]] = []
        for row in rows:
            if type(row["title"]) is not str or not row["title"].strip():
                return _blocked("TITLE_INVALID")
            stamp = datetime.fromisoformat(row["observed_at"].replace("Z", "+00:00")).astimezone(timezone.utc)
            timestamp = stamp.isoformat().replace("+00:00", "Z")
            item: dict[str, Any] = {
                "title": row["title"],
                "api_observed_at": timestamp,
                "transparency_notice": contract.TRANSPARENCY_NOTICE,
            }
            if type(row["price_min"]) is not int or row["price_min"] < 0:
                return _blocked("PRICE_INVALID")
            item.update({"current_price": row["price_min"], "price_observed_at": timestamp})
            items.append(item)
        packet = {
            "version": renderer.PACKET_VERSION,
            "mode": contract.PRESENTATION_MODE,
            "as_of": as_of,
            "transparency_notice": contract.TRANSPARENCY_NOTICE,
            "candidates": items,
            "publication_allowed": False,
            "production_activation_allowed": False,
            "affiliate_eligibility_allowed": False,
            "gate_mutation_allowed": False,
            "cta_allowed": False,
        }
        packet_bytes = json.dumps(
            packet, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        payloads: list[bytes] = []
        durations: list[float] = []
        for _ in range(REPETITIONS):
            started = perf_counter_ns()
            payload, receipt = renderer.render(
                packet_bytes, evaluated_at=evaluated_at, target_route="/items/"
            )
            durations.append((perf_counter_ns() - started) / 1_000_000)
            if receipt.candidate_count != TARGET_COUNT or receipt.output_written:
                return _blocked("RENDER_RECEIPT_INVALID")
            payloads.append(payload)
        if _digest(database) != before:
            return _blocked("DATABASE_CHANGED_DURING_VERIFICATION")
        first = payloads[0]
        deterministic = all(payload == first for payload in payloads[1:])
        structure = (
            first.count(b'<article class="item">') == TARGET_COUNT
            and b'<meta name="robots" content="noindex,nofollow">' in first
            and b'https://datalabx.jp/items/' in first
            and b'affiliateURL' not in first
            and b'content_id' not in first
        )
        maximum = max(durations)
        reasons: set[str] = set()
        if not deterministic:
            reasons.add("RENDER_NOT_DETERMINISTIC")
        if not structure:
            reasons.add("RENDERED_STRUCTURE_INVALID")
        if maximum > MAX_RENDER_MILLISECONDS:
            reasons.add("RENDER_TIME_BUDGET_EXCEEDED")
        if len(first) > MAX_ARTIFACT_BYTES:
            reasons.add("ARTIFACT_SIZE_BUDGET_EXCEEDED")
        return RenderPerformanceReceipt(
            VERSION, VERIFIED if not reasons else BLOCKED, TARGET_COUNT,
            REPETITIONS, round(maximum, 3), len(first), deterministic, structure,
            before, hashlib.sha256(first).hexdigest(), False, False,
            False, False, False, tuple(sorted(reasons)),
        )
    except (OSError, sqlite3.Error, ValueError, TypeError, renderer.CandidateFailure):
        return _blocked("VERIFICATION_FAILED")
    finally:
        if connection is not None:
            connection.close()


__all__ = ["RenderPerformanceReceipt", "verify"]
