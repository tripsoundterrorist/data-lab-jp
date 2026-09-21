"""Generate lifecycle receipts from sanitized saved observations.

Legacy snapshots and snapshots without a strictly bound sanitized lifecycle
row remain UNKNOWN.  Raw provider payloads, URLs, identifiers, and credentials
are never read into the receipt contract.
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
PACKET_VERSION = "0.2"
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

LEGACY_SAVED_OBSERVATIONS_SQL = """
SELECT i.id, i.site, i.service, i.floor, i.content_id, i.last_observed_at,
       s.latest_snapshot_id, s.latest_observed_at,
       NULL AS lifecycle_snapshot_id, NULL AS lifecycle_contract_version,
       NULL AS verification_mode, NULL AS lifecycle_observation,
       NULL AS lifecycle_observed_at, NULL AS expected_content_id_match,
       NULL AS affiliate_link_observed, NULL AS source_status_code,
       NULL AS inventory_signal, NULL AS reason_code, NULL AS created_at
FROM items AS i
LEFT JOIN (
  SELECT snapshots.id AS latest_snapshot_id, snapshots.item_id,
         snapshots.observed_at AS latest_observed_at
  FROM item_snapshots AS snapshots
  JOIN (
    SELECT item_id, MAX(observed_at) AS latest_observed_at
    FROM item_snapshots
    GROUP BY item_id
  ) AS latest
    ON latest.item_id = snapshots.item_id
   AND latest.latest_observed_at = snapshots.observed_at
) AS s ON s.item_id = i.id
ORDER BY i.id, s.latest_snapshot_id
"""

SAVED_OBSERVATIONS_SQL = """
SELECT i.id, i.site, i.service, i.floor, i.content_id, i.last_observed_at,
       s.latest_snapshot_id, s.latest_observed_at,
       o.snapshot_id AS lifecycle_snapshot_id,
       o.contract_version AS lifecycle_contract_version,
       o.verification_mode, o.observation AS lifecycle_observation,
       o.observed_at AS lifecycle_observed_at,
       o.expected_content_id_match, o.affiliate_link_observed,
       o.source_status_code, o.inventory_signal, o.reason_code, o.created_at
FROM items AS i
LEFT JOIN (
  SELECT snapshots.id AS latest_snapshot_id, snapshots.item_id,
         snapshots.observed_at AS latest_observed_at
  FROM item_snapshots AS snapshots
  JOIN (
    SELECT item_id, MAX(observed_at) AS latest_observed_at
    FROM item_snapshots
    GROUP BY item_id
  ) AS latest
    ON latest.item_id = snapshots.item_id
   AND latest.latest_observed_at = snapshots.observed_at
) AS s ON s.item_id = i.id
LEFT JOIN item_lifecycle_observations AS o
  ON o.snapshot_id = s.latest_snapshot_id
ORDER BY i.id, s.latest_snapshot_id
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


def _has_lifecycle_observation_table(connection: sqlite3.Connection) -> bool:
    row = connection.execute(
        """
        SELECT COUNT(*) FROM sqlite_master
        WHERE type = 'table' AND name = 'item_lifecycle_observations'
        """
    ).fetchone()
    return row is not None and row[0] == 1


def _stored_observation(
    row: sqlite3.Row,
    *,
    snapshot_time: str,
) -> tuple[VerificationObservation, InventorySignal]:
    if row["lifecycle_snapshot_id"] is None:
        raise SavedReceiptError("SAVED_LIFECYCLE_OBSERVATION_MISSING")
    if (
        row["lifecycle_snapshot_id"] != row["latest_snapshot_id"]
        or row["lifecycle_contract_version"] != "0.1"
        or row["verification_mode"] != "COLLECTION_PAGE_ITEM"
        or row["lifecycle_observation"] != Observation.API_ITEM_VISIBLE.value
        or row["lifecycle_observed_at"] != snapshot_time
        or row["expected_content_id_match"] != 1
        or row["source_status_code"] != 200
        or row["inventory_signal"] != InventorySignal.UNKNOWN.value
        or row["reason_code"] not in {
            "AFFILIATE_URL_ABSENT",
            "AFFILIATE_URL_VALIDATED",
            "AFFILIATE_URL_VALIDATION_FAILED",
        }
    ):
        raise SavedReceiptError("SAVED_LIFECYCLE_OBSERVATION_INVALID")
    affiliate_value = row["affiliate_link_observed"]
    expected_reason = {
        1: "AFFILIATE_URL_VALIDATED",
        0: "AFFILIATE_URL_ABSENT",
        None: "AFFILIATE_URL_VALIDATION_FAILED",
    }.get(affiliate_value)
    if expected_reason is None or row["reason_code"] != expected_reason:
        raise SavedReceiptError("SAVED_AFFILIATE_OBSERVATION_INVALID")
    observed_at = parse_timestamp(row["lifecycle_observed_at"])
    created_at = parse_timestamp(row["created_at"])
    if created_at < observed_at:
        raise SavedReceiptError("SAVED_LIFECYCLE_TIME_INVALID")
    return (
        VerificationObservation(
            Observation.API_ITEM_VISIBLE,
            observed_at,
            True,
            None if affiliate_value is None else bool(affiliate_value),
            200,
            tuple(sorted((
                "COLLECTION_ITEM_IDENTITY_MATCH_OBSERVED",
                row["reason_code"],
            ))),
        ),
        InventorySignal.UNKNOWN,
    )


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
            sql = (
                SAVED_OBSERVATIONS_SQL
                if _has_lifecycle_observation_table(connection)
                else LEGACY_SAVED_OBSERVATIONS_SQL
            )
            rows = connection.execute(sql)
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
                    observation = VerificationObservation(
                        Observation.UNKNOWN,
                        None,
                        None,
                        None,
                        None,
                        reasons,
                    )
                    inventory = InventorySignal.UNKNOWN
                else:
                    observed_at = parse_timestamp(snapshot_time)
                    if master_time != snapshot_time:
                        raise SavedReceiptError("SAVED_OBSERVATION_ITEM_MISMATCH")
                    age = evaluated_at - observed_at
                    fresh = timedelta(0) <= age <= freshness_max_age
                    if row["lifecycle_snapshot_id"] is None:
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
                        inventory = InventorySignal.UNKNOWN
                    else:
                        observation, inventory = _stored_observation(
                            row,
                            snapshot_time=snapshot_time,
                        )
                        if observation.observed_at != observed_at:
                            raise SavedReceiptError(
                                "SAVED_LIFECYCLE_SNAPSHOT_TIME_MISMATCH"
                            )
                receipts.append(
                    LifecycleReceipt(
                        LIFECYCLE_RECEIPT_VERSION,
                        public_id,
                        observation,
                        inventory,
                        fresh,
                        evaluated_at,
                        int(freshness_max_age.total_seconds()),
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
        "freshness_evaluated_at": (
            iso_utc(receipt.freshness_evaluated_at)
            if receipt.freshness_evaluated_at is not None else None
        ),
        "freshness_max_age_seconds": receipt.freshness_max_age_seconds,
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
            "freshness_confirmed", "freshness_evaluated_at",
            "freshness_max_age_seconds",
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
            or (
                observed["source_status_code"] is not None
                and (
                    type(observed["source_status_code"]) is not int
                    or not 100 <= observed["source_status_code"] <= 599
                )
            )
            or not isinstance(reasons, list)
            or not reasons
            or any(not isinstance(reason, str) or REASON_RE.fullmatch(reason) is None for reason in reasons)
        ):
            raise SavedReceiptError("RECEIPT_VALUE_INVALID")
        age = as_of - observed_at if observed_at is not None else None
        expected_fresh = age is not None and timedelta(0) <= age <= timedelta(seconds=max_age)
        freshness_evaluated_at = parse_timestamp(value["freshness_evaluated_at"])
        if (
            value["freshness_max_age_seconds"] != max_age
            or freshness_evaluated_at != as_of
            or value["freshness_confirmed"] is not expected_fresh
        ):
            raise SavedReceiptError("RECEIPT_FRESHNESS_MISMATCH")
        if inventory is not InventorySignal.UNKNOWN:
            raise SavedReceiptError("SAVED_RECEIPT_EVIDENCE_OVERCLAIMED")
        if observation_value is Observation.UNKNOWN:
            expected_reasons = (
                ("SAVED_OBSERVATION_MISSING",)
                if observed_at is None
                else (
                    "SAVED_AFFILIATE_EVIDENCE_UNAVAILABLE",
                    "SAVED_COLLECTION_NOT_EXACT_ITEM_VERIFICATION",
                ) + (() if expected_fresh else ("SAVED_OBSERVATION_STALE_OR_FUTURE",))
            )
            valid_shape = (
                observed["expected_content_id_match"] is None
                and observed["affiliate_link_observed"] is None
                and observed["source_status_code"] is None
                and tuple(reasons) == expected_reasons
            )
        elif observation_value is Observation.API_ITEM_VISIBLE:
            affiliate_reason = {
                True: "AFFILIATE_URL_VALIDATED",
                False: "AFFILIATE_URL_ABSENT",
                None: "AFFILIATE_URL_VALIDATION_FAILED",
            }[observed["affiliate_link_observed"]]
            valid_shape = (
                observed_at is not None
                and observed["expected_content_id_match"] is True
                and observed["source_status_code"] == 200
                and tuple(reasons) == tuple(sorted((
                    "COLLECTION_ITEM_IDENTITY_MATCH_OBSERVED",
                    affiliate_reason,
                )))
            )
        else:
            valid_shape = False
        if not valid_shape:
            raise SavedReceiptError("SAVED_RECEIPT_EVIDENCE_OVERCLAIMED")
        receipts.append(
            LifecycleReceipt(
                value["version"], public_id,
                VerificationObservation(
                    observation_value, observed_at,
                    observed["expected_content_id_match"],
                    observed["affiliate_link_observed"],
                    observed["source_status_code"], tuple(reasons),
                ),
                inventory, value["freshness_confirmed"],
                freshness_evaluated_at, max_age,
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
