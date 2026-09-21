"""Build a sanitized, unordered, review-only packet from saved DB evidence."""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from typing import Any

from product_verification import Observation, VerificationObservation
import revenue_mvp_official_lifecycle_policy as lifecycle
import revenue_mvp_unordered_surface_review as contract

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.1-candidate"
MAX_AGE = timedelta(hours=24)
FORBIDDEN_KEYS = contract.FORBIDDEN_PUBLIC_FIELDS | frozenset(
    {"item_id", "snapshot_id", "public_id", "affiliate_link_observed", "reason_code"}
)

QUERY = """
WITH latest AS (
  SELECT s.*,
         ROW_NUMBER() OVER (PARTITION BY s.item_id ORDER BY s.observed_at DESC, s.id DESC) AS rn
  FROM item_snapshots AS s
)
SELECT s.observed_at, s.price_min, t.title,
       t.observed_at AS title_observed_at,
       o.observed_at AS lifecycle_observed_at,
       o.expected_content_id_match, o.affiliate_link_observed,
       o.source_status_code, o.inventory_signal
FROM latest AS s
JOIN item_snapshot_titles AS t ON t.snapshot_id = s.id
JOIN item_lifecycle_observations AS o ON o.snapshot_id = s.id
WHERE s.rn = 1
ORDER BY s.id
"""


@dataclass(frozen=True)
class ReviewPacketResult:
    version: str
    status: str
    candidate_count: int
    packet_sha256: str | None
    output_written: bool
    publication_allowed: bool = False
    production_activation_allowed: bool = False
    affiliate_eligibility_allowed: bool = False
    gate_mutation_allowed: bool = False
    cta_allowed: bool = False
    api_calls: int = 0
    network_io_performed: bool = False
    production_write_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PacketFailure(Exception):
    pass


def parse_timestamp(value: Any) -> datetime:
    if type(value) is not str:
        raise PacketFailure("TIMESTAMP_INVALID")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise PacketFailure("TIMESTAMP_INVALID") from error
    if parsed.tzinfo is None:
        raise PacketFailure("TIMESTAMP_INVALID")
    return parsed.astimezone(timezone.utc)


def iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sidecars_present(path: Path) -> bool:
    return any(Path(f"{path}{suffix}").exists() for suffix in ("-wal", "-shm", "-journal"))


def _packet_bytes(candidates: list[dict[str, Any]], as_of: datetime) -> bytes:
    packet = {
        "version": VERSION,
        "mode": contract.PRESENTATION_MODE,
        "as_of": iso_utc(as_of),
        "transparency_notice": contract.TRANSPARENCY_NOTICE,
        "candidates": candidates,
        "publication_allowed": False,
        "production_activation_allowed": False,
        "affiliate_eligibility_allowed": False,
        "gate_mutation_allowed": False,
        "cta_allowed": False,
    }
    encoded = json.dumps(
        packet, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8") + b"\n"
    decoded = json.loads(encoded)
    for candidate in decoded["candidates"]:
        if set(candidate) & FORBIDDEN_KEYS:
            raise PacketFailure("FORBIDDEN_FIELD_PRESENT")
    return encoded


def build_packet(database: Path, expected_sha256: str, as_of: datetime) -> bytes:
    database = database.resolve()
    if not database.is_file() or len(expected_sha256) != 64:
        raise PacketFailure("DATABASE_IDENTITY_INVALID")
    if _sidecars_present(database) or file_sha256(database) != expected_sha256:
        raise PacketFailure("DATABASE_IDENTITY_INVALID")
    connection = sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only = ON")
        required = {"item_snapshots", "item_snapshot_titles", "item_lifecycle_observations"}
        tables = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if not required <= tables:
            raise PacketFailure("REQUIRED_SCHEMA_MISSING")
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise PacketFailure("INTEGRITY_CHECK_FAILED")
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise PacketFailure("FOREIGN_KEY_CHECK_FAILED")
        candidates: list[dict[str, Any]] = []
        for row in connection.execute(QUERY):
            observed = parse_timestamp(row["observed_at"])
            if not timedelta(0) <= as_of - observed <= MAX_AGE:
                continue
            if row["title_observed_at"] != row["observed_at"] or row[
                "lifecycle_observed_at"
            ] != row["observed_at"]:
                continue
            observation = VerificationObservation(
                Observation.API_ITEM_VISIBLE,
                observed,
                row["expected_content_id_match"] == 1,
                row["affiliate_link_observed"] == 1,
                row["source_status_code"],
                ("AFFILIATE_URL_VALIDATED",),
            )
            decision = lifecycle.evaluate_official_lifecycle_policy(
                observation, inventory_signal=row["inventory_signal"]
            )
            fields = {"title", "api_observed_at", "transparency_notice"}
            claims = {"API_OBSERVED_AT", "UNORDERED_PRESENTATION"}
            price_observed_at = None
            if row["price_min"] is not None:
                fields.update({"current_price", "price_observed_at"})
                claims.add("PRICE_OBSERVED_AT")
                price_observed_at = observed
            reviewed = contract.review_unordered_surface(
                decision,
                contract_version=contract.CONTRACT_VERSION,
                lifecycle_freshness_confirmed=True,
                api_observed_at=observed,
                public_fields=fields,
                public_claim_codes=claims,
                presentation_mode=contract.PRESENTATION_MODE,
                sort_controls_present=False,
                position_indicators_present=False,
                history_present=False,
                affiliate_cta_requested=False,
                title_snapshot_provenance_confirmed=True,
                transparency_notice=contract.TRANSPARENCY_NOTICE,
                price_observed_at=price_observed_at,
            )
            if not reviewed.eligible_for_manual_gate_review:
                continue
            candidate = {
                "title": row["title"],
                "api_observed_at": iso_utc(observed),
                "transparency_notice": contract.TRANSPARENCY_NOTICE,
            }
            if row["price_min"] is not None:
                candidate["current_price"] = row["price_min"]
                candidate["price_observed_at"] = iso_utc(observed)
            candidates.append(candidate)
    except (sqlite3.Error, TypeError, ValueError) as error:
        raise PacketFailure("DATABASE_OR_EVIDENCE_INVALID") from error
    finally:
        connection.close()
    if _sidecars_present(database) or file_sha256(database) != expected_sha256:
        raise PacketFailure("DATABASE_CHANGED_DURING_REVIEW")
    return _packet_bytes(candidates, as_of)


def write_atomic(path: Path, payload: bytes) -> None:
    target = path.resolve()
    try:
        target.relative_to(ROOT.resolve())
    except ValueError:
        pass
    else:
        raise PacketFailure("OUTPUT_MUST_BE_OUTSIDE_REPOSITORY")
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix="unordered-review-", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
        os.replace(temporary, target)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def run(database: Path, expected_sha256: str, as_of: datetime, output: Path | None = None) -> ReviewPacketResult:
    payload = build_packet(database, expected_sha256, as_of)
    packet = json.loads(payload)
    if output is not None:
        write_atomic(output, payload)
    return ReviewPacketResult(
        VERSION,
        "UNORDERED_REVIEW_PACKET_READY",
        len(packet["candidates"]),
        hashlib.sha256(payload).hexdigest(),
        output is not None,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--as-of", required=True, type=parse_timestamp)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        result = run(args.db, args.expected_sha256, args.as_of, args.output)
    except (PacketFailure, OSError):
        print("unordered_review_status: blocked", file=sys.stderr)
        return 1
    print(json.dumps(result.to_dict(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
