"""Build one offline, review-only CTA packet from immutable saved evidence."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any

from revenue_mvp_lifecycle_receipt import public_item_id
import revenue_mvp_minimal_opaque_go_cta_contract as cta_contract
import revenue_mvp_unordered_review_packet as unordered


VERSION = "0.1-candidate"
READY = "MINIMAL_OPAQUE_GO_CTA_PACKET_READY"


class CtaPacketFailure(ValueError):
    pass


@dataclass(frozen=True)
class CtaPacketReceipt:
    version: str
    status: str
    candidate_count: int
    source_candidate_count: int
    source_packet_sha256: str
    packet_sha256: str
    api_calls: int = 0
    network_io_performed: bool = False
    production_write_performed: bool = False
    publication_allowed: bool = False
    production_activation_allowed: bool = False
    affiliate_eligibility_allowed: bool = False
    gate_mutation_allowed: bool = False
    deployment_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _identity_rows(database: Path) -> list[sqlite3.Row]:
    connection = sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only = ON")
        return list(connection.execute("""
            WITH latest AS (
              SELECT s.*,
                     ROW_NUMBER() OVER (
                       PARTITION BY s.item_id ORDER BY s.observed_at DESC, s.id DESC
                     ) AS rn
              FROM item_snapshots AS s
            )
            SELECT i.site, i.service, i.floor, i.content_id,
                   s.observed_at, s.price_min, t.title
            FROM latest AS s
            JOIN items AS i ON i.id = s.item_id
            JOIN item_snapshot_titles AS t ON t.snapshot_id = s.id
            JOIN item_lifecycle_observations AS o ON o.snapshot_id = s.id
            WHERE s.rn = 1
              AND t.observed_at = s.observed_at
              AND o.observed_at = s.observed_at
            ORDER BY s.id
        """))
    except sqlite3.Error as error:
        raise CtaPacketFailure("DATABASE_READ_FAILED") from error
    finally:
        connection.close()


def _candidate_key(candidate: dict[str, Any]) -> tuple[Any, ...]:
    return (
        candidate.get("title"), candidate.get("api_observed_at"),
        candidate.get("current_price") if "current_price" in candidate else None,
        "current_price" in candidate,
    )


def build_packet(
    database: Path, expected_sha256: str, as_of: datetime
) -> tuple[bytes, CtaPacketReceipt]:
    """Bind exactly one reviewed candidate to its DB-derived opaque ID."""

    source = unordered.build_packet(database, expected_sha256, as_of)
    source_value = json.loads(source)
    candidates = source_value.get("candidates")
    if type(candidates) is not list or not candidates:
        raise CtaPacketFailure("REVIEWED_CANDIDATE_REQUIRED")

    database = database.resolve()
    if unordered._sidecars_present(database) or unordered.file_sha256(database) != expected_sha256:
        raise CtaPacketFailure("DATABASE_IDENTITY_INVALID")
    rows_by_key: dict[tuple[Any, ...], list[sqlite3.Row]] = {}
    for row in _identity_rows(database):
        observed = unordered.iso_utc(unordered.parse_timestamp(row["observed_at"]))
        row_key = (
            row["title"], observed, row["price_min"], row["price_min"] is not None,
        )
        rows_by_key.setdefault(row_key, []).append(row)
    bound: list[tuple[str, dict[str, Any], sqlite3.Row]] = []
    for candidate in candidates:
        matches = rows_by_key.get(_candidate_key(candidate), [])
        if len(matches) != 1:
            raise CtaPacketFailure("OPAQUE_ID_BINDING_NOT_UNIQUE")
        row = matches[0]
        values = (row["site"], row["service"], row["floor"], row["content_id"])
        if not all(type(value) is str and value for value in values):
            raise CtaPacketFailure("SOURCE_IDENTITY_INVALID")
        bound.append((public_item_id(*values), candidate, row))
    bound.sort(key=lambda value: value[0])
    opaque_id, candidate, row = bound[0]
    review = cta_contract.review({
        "contract_version": cta_contract.VERSION,
        "public_id": opaque_id,
        "cta_href": f"/go/{opaque_id}",
        "disclosure_text": cta_contract.DISCLOSURE,
        "disclosure_proximate": True,
        "affiliate_url_exposed": False,
        "server_side_lookup_required": True,
        "rate_limit_required": True,
        "publication_scope_expanded": True,
        "exact_unordered_scope_unchanged": True,
    })
    if not review.eligible_for_implementation_review:
        raise CtaPacketFailure("CTA_CONTRACT_BLOCKED")
    if unordered._sidecars_present(database) or unordered.file_sha256(database) != expected_sha256:
        raise CtaPacketFailure("DATABASE_CHANGED_DURING_BINDING")

    public_candidate = dict(candidate)
    public_candidate.update({
        "public_id": opaque_id,
        "cta_href": f"/go/{opaque_id}",
        "disclosure_text": cta_contract.DISCLOSURE,
        "disclosure_proximate": True,
    })
    packet = {
        "version": VERSION,
        "source_packet_sha256": hashlib.sha256(source).hexdigest(),
        "as_of": source_value["as_of"],
        "selection_method": "OPAQUE_ID_LEXICOGRAPHIC_MIN_NO_RANKING_MEANING",
        "source_candidate_count": len(candidates),
        "candidates": [public_candidate],
        "publication_allowed": False,
        "production_activation_allowed": False,
        "affiliate_eligibility_allowed": False,
        "gate_mutation_allowed": False,
        "deployment_allowed": False,
    }
    payload = json.dumps(
        packet, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8") + b"\n"
    text = payload.decode("utf-8")
    for forbidden in (row["content_id"], "affiliateURL", "DMM_API_ID", "DMM_AFFILIATE_ID"):
        if forbidden in text:
            raise CtaPacketFailure("PRIVATE_VALUE_EXPOSURE_BLOCKED")
    receipt = CtaPacketReceipt(
        VERSION, READY, 1, len(candidates), packet["source_packet_sha256"],
        hashlib.sha256(payload).hexdigest(),
    )
    return payload, receipt


__all__ = [
    "CtaPacketFailure", "CtaPacketReceipt", "READY", "VERSION", "build_packet",
]
