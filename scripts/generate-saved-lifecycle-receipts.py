"""Generate sanitized lifecycle receipts from saved read-only observations.

Saved collection rows do not prove an exact item lookup or affiliate-link
presence. They therefore generate UNKNOWN receipts and never create an eligible
candidate. A future bounded live verifier may produce stronger evidence.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import tempfile
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from product_verification import Observation, VerificationObservation
from revenue_mvp_lifecycle_receipt import (
    LIFECYCLE_RECEIPT_VERSION,
    LifecycleReceipt,
    public_item_id,
)
from revenue_mvp_official_lifecycle_policy import InventorySignal


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_PATH = ROOT / "data" / "data-lab.db"
PACKET_VERSION = "0.1"
DEFAULT_FRESHNESS_MAX_AGE = timedelta(hours=24)
PUBLIC_ID_RE = re.compile(r"itm_[0-9a-f]{24}\Z")
REASON_RE = re.compile(r"[A-Z][A-Z0-9_]{2,63}\Z")
FORBIDDEN_KEYS = frozenset(
    {
        "api_id", "affiliate_id", "affiliate_url", "affiliateurl",
        "content_id", "raw_response", "raw_api_response", "credential",
        "credentials", "item_url", "query_context_json", "source_offset",
        "source_position",
    }
)

SAVED_OBSERVATIONS_SQL = """
SELECT i.id, i.site, i.service, i.floor, i.content_id, i.last_observed_at,
       s.latest_observed_at
FROM items AS i
LEFT JOIN (
  SELECT item_id, MAX(observed_at) AS latest_observed_at
  FROM item_snapshots
  GROUP BY item_id
) AS s ON s.item_id = i.id
ORDER BY i.id
"""


class SavedReceiptError(Exception):
    pass


def parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise SavedReceiptError("SAVED_OBSERVATION_TIMESTAMP_INVALID")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise SavedReceiptError("SAVED_OBSERVATION_TIMESTAMP_INVALID") from error
    if parsed.tzinfo is None:
        raise SavedReceiptError("SAVED_OBSERVATION_TIMESTAMP_INVALID")
    return parsed.astimezone(timezone.utc)


def iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def read_only_connection(path: Path) -> sqlite3.Connection:
    resolved = path.resolve()
    if not resolved.is_file():
        raise SavedReceiptError("DATABASE_NOT_FOUND")
    connection = sqlite3.connect(f"{resolved.as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def generate_receipts(
    database_path: Path,
    *,
    as_of: datetime,
    freshness_max_age: timedelta = DEFAULT_FRESHNESS_MAX_AGE,
) -> tuple[LifecycleReceipt, ...]:
    if as_of.tzinfo is None or freshness_max_age <= timedelta(0):
        raise SavedReceiptError("GENERATOR_ARGUMENT_INVALID")
    evaluated_at = as_of.astimezone(timezone.utc)
    receipts: list[LifecycleReceipt] = []
    seen_public_ids: set[str] = set()
    try:
        with closing(read_only_connection(database_path)) as connection:
            rows = connection.execute(SAVED_OBSERVATIONS_SQL)
            for row in rows:
                identity = (row["site"], row["service"], row["floor"], row["content_id"])
                if not all(isinstance(value, str) and value for value in identity):
                    raise SavedReceiptError("SAVED_ITEM_IDENTITY_INVALID")
                public_id = public_item_id(*identity)
                if public_id in seen_public_ids:
                    raise SavedReceiptError("DUPLICATE_PUBLIC_ID")
                seen_public_ids.add(public_id)

                master_time = row["last_observed_at"]
                snapshot_time = row["latest_observed_at"]
                if snapshot_time is None:
                    observed_at = None
                    fresh = False
                    reasons = ("SAVED_OBSERVATION_MISSING",)
                else:
                    observed_at = parse_timestamp(snapshot_time)
                    if master_time != snapshot_time:
                        raise SavedReceiptError("SAVED_OBSERVATION_ITEM_MISMATCH")
                    age = evaluated_at - observed_at
                    fresh = timedelta(0) <= age <= freshness_max_age
                    reasons = (
                        "SAVED_COLLECTION_NOT_EXACT_ITEM_VERIFICATION",
                        "SAVED_AFFILIATE_EVIDENCE_UNAVAILABLE",
                    )
                    if not fresh:
                        reasons += ("SAVED_OBSERVATION_STALE_OR_FUTURE",)
                observation = VerificationObservation(
                    Observation.UNKNOWN,
                    observed_at,
                    None,
                    None,
                    None,
                    tuple(sorted(reasons)),
                )
                receipts.append(
                    LifecycleReceipt(
                        LIFECYCLE_RECEIPT_VERSION,
                        public_id,
                        observation,
                        InventorySignal.UNKNOWN,
                        fresh,
                    )
                )
    except sqlite3.Error as error:
        raise SavedReceiptError("SAVED_OBSERVATION_READ_FAILED") from error
    return tuple(receipts)


def receipt_to_dict(receipt: LifecycleReceipt) -> dict[str, Any]:
    return {
        "version": receipt.version,
        "public_id": receipt.public_id,
        "observation": {
            "observation": receipt.observation.observation.value,
            "observed_at": (
                iso_utc(receipt.observation.observed_at)
                if receipt.observation.observed_at is not None else None
            ),
            "expected_content_id_match": receipt.observation.expected_content_id_match,
            "affiliate_link_observed": receipt.observation.affiliate_link_observed,
            "source_status_code": receipt.observation.source_status_code,
            "reason_codes": list(receipt.observation.reason_codes),
        },
        "inventory_signal": receipt.inventory_signal.value,
        "freshness_confirmed": receipt.freshness_confirmed,
    }


def validate_packet(packet: Any) -> tuple[LifecycleReceipt, ...]:
    if not isinstance(packet, dict) or set(packet) != {
        "version", "as_of", "freshness_max_age_seconds", "receipts"
    }:
        raise SavedReceiptError("PACKET_FIELDS_INVALID")
    if packet["version"] != PACKET_VERSION:
        raise SavedReceiptError("PACKET_VERSION_INVALID")
    as_of = parse_timestamp(packet["as_of"])
    max_age = packet["freshness_max_age_seconds"]
    if isinstance(max_age, bool) or not isinstance(max_age, int) or max_age <= 0:
        raise SavedReceiptError("PACKET_FRESHNESS_INVALID")
    values = packet["receipts"]
    if not isinstance(values, list):
        raise SavedReceiptError("PACKET_RECEIPTS_INVALID")
    receipts: list[LifecycleReceipt] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, dict) or set(value) != {
            "version", "public_id", "observation", "inventory_signal",
            "freshness_confirmed",
        }:
            raise SavedReceiptError("RECEIPT_FIELDS_INVALID")
        public_id = value["public_id"]
        if not isinstance(public_id, str) or PUBLIC_ID_RE.fullmatch(public_id) is None:
            raise SavedReceiptError("RECEIPT_PUBLIC_ID_INVALID")
        if public_id in seen:
            raise SavedReceiptError("DUPLICATE_PUBLIC_ID")
        seen.add(public_id)
        observed = value["observation"]
        if not isinstance(observed, dict) or set(observed) != {
            "observation", "observed_at", "expected_content_id_match",
            "affiliate_link_observed", "source_status_code", "reason_codes",
        }:
            raise SavedReceiptError("OBSERVATION_FIELDS_INVALID")
        try:
            observation_value = Observation(observed["observation"])
            inventory = InventorySignal(value["inventory_signal"])
        except (TypeError, ValueError) as error:
            raise SavedReceiptError("RECEIPT_ENUM_INVALID") from error
        observed_at = (
            parse_timestamp(observed["observed_at"])
            if observed["observed_at"] is not None else None
        )
        reasons = observed["reason_codes"]
        if (
            value["version"] != LIFECYCLE_RECEIPT_VERSION
            or type(value["freshness_confirmed"]) is not bool
            or observed["expected_content_id_match"] not in (True, False, None)
            or observed["affiliate_link_observed"] not in (True, False, None)
            or observed["source_status_code"] is not None
            or not isinstance(reasons, list)
            or not reasons
            or any(not isinstance(reason, str) or REASON_RE.fullmatch(reason) is None for reason in reasons)
        ):
            raise SavedReceiptError("RECEIPT_VALUE_INVALID")
        age = as_of - observed_at if observed_at is not None else None
        expected_fresh = age is not None and timedelta(0) <= age <= timedelta(seconds=max_age)
        if value["freshness_confirmed"] is not expected_fresh:
            raise SavedReceiptError("RECEIPT_FRESHNESS_MISMATCH")
        expected_reasons = (
            ("SAVED_OBSERVATION_MISSING",)
            if observed_at is None
            else (
                "SAVED_AFFILIATE_EVIDENCE_UNAVAILABLE",
                "SAVED_COLLECTION_NOT_EXACT_ITEM_VERIFICATION",
            ) + (() if expected_fresh else ("SAVED_OBSERVATION_STALE_OR_FUTURE",))
        )
        if (
            observation_value is not Observation.UNKNOWN
            or inventory is not InventorySignal.UNKNOWN
            or observed["expected_content_id_match"] is not None
            or observed["affiliate_link_observed"] is not None
            or tuple(reasons) != expected_reasons
        ):
            raise SavedReceiptError("SAVED_RECEIPT_EVIDENCE_OVERCLAIMED")
        receipts.append(
            LifecycleReceipt(
                value["version"], public_id,
                VerificationObservation(
                    observation_value, observed_at,
                    observed["expected_content_id_match"],
                    observed["affiliate_link_observed"], None, tuple(reasons),
                ),
                inventory, value["freshness_confirmed"],
            )
        )
    return tuple(receipts)


def create_packet(receipts: tuple[LifecycleReceipt, ...], *, as_of: datetime,
                  freshness_max_age: timedelta = DEFAULT_FRESHNESS_MAX_AGE) -> dict[str, Any]:
    packet = {
        "version": PACKET_VERSION,
        "as_of": iso_utc(as_of),
        "freshness_max_age_seconds": int(freshness_max_age.total_seconds()),
        "receipts": [receipt_to_dict(receipt) for receipt in receipts],
    }
    validate_packet(packet)
    return packet


def safety_scan(packet: dict[str, Any]) -> None:
    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key.casefold() in FORBIDDEN_KEYS:
                    raise SavedReceiptError("PACKET_FORBIDDEN_FIELD")
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(packet)


def write_isolated_packet(path: Path, packet: dict[str, Any]) -> None:
    resolved = path.resolve()
    try:
        resolved.relative_to(ROOT.resolve())
    except ValueError:
        pass
    else:
        raise SavedReceiptError("OUTPUT_MUST_BE_OUTSIDE_REPOSITORY")
    safety_scan(packet)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix="receipt-", suffix=".tmp", dir=resolved.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(packet, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
        os.replace(temporary_name, resolved)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate sanitized saved-observation lifecycle receipts")
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE_PATH)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        as_of = parse_timestamp(args.as_of)
        receipts = generate_receipts(args.database, as_of=as_of)
        packet = create_packet(receipts, as_of=as_of)
        safety_scan(packet)
        if args.output is not None:
            write_isolated_packet(args.output, packet)
        candidate_count = sum(
            receipt.observation.observation is Observation.API_ITEM_VISIBLE
            and receipt.observation.affiliate_link_observed is True
            and receipt.freshness_confirmed is True
            for receipt in receipts
        )
        print(json.dumps({
            "status": "LOCAL_VALIDATION_ONLY",
            "receipt_count": len(receipts),
            "candidate_count": candidate_count,
            "output_written": args.output is not None,
            "api_calls": 0,
            "database_writes": 0,
        }, sort_keys=True))
        return 0
    except (OSError, SavedReceiptError, ValueError):
        print("saved lifecycle receipt generation failed: FAIL_CLOSED", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
