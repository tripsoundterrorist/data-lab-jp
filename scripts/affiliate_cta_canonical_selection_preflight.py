"""One-shot canonical CTA selection preflight with no default live capability."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

import affiliate_cta_canary_preflight as existing
import affiliate_cta_exact_selection as exact

VERSION = "0.1-candidate"
CANONICALIZATION_VERSION = "data-lab-affiliate-cta-selection-v1"
READY = "CANONICAL_SELECTION_READY_FOR_EXACT_REVIEW"
BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class CanonicalSelectionReceipt:
    version: str
    canonicalization_version: str
    status: str
    source_database_sha256: str | None
    live_artifact_sha256: str | None
    selection_digest: str | None
    submitted_count: int
    api_request_attempt_count: int
    selected_count: int
    identifiers_exposed: bool = False
    affiliate_urls_exposed: bool = False
    production_write_performed: bool = False
    cta_activation_allowed: bool = False
    d1_write_allowed: bool = False
    deployment_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run(
    public_ids: Any,
    *,
    as_of: Any,
    execution_authorized: Any,
    one_shot: Any,
    source_database_sha256: Any,
    live_artifact_sha256: Any,
    resolve_content_id: Any,
    fetch_sanitized_item_payload: Any,
    plan: Any,
) -> CanonicalSelectionReceipt:
    """Return hashes and counts only; callbacks are absent from the default path."""
    count = len(public_ids) if type(public_ids) is tuple else 0
    if (
        execution_authorized is not True
        or one_shot is not True
        or type(source_database_sha256) is not str
        or len(source_database_sha256) != 64
        or type(live_artifact_sha256) is not str
        or len(live_artifact_sha256) != 64
    ):
        return CanonicalSelectionReceipt(
            VERSION, CANONICALIZATION_VERSION, BLOCKED, None, None, None, count, 0, 0
        )
    result = existing.run_preflight(
        public_ids,
        as_of=as_of,
        execution_authorized=True,
        one_shot=True,
        resolve_content_id=resolve_content_id,
        fetch_sanitized_item_payload=fetch_sanitized_item_payload,
        plan=plan,
    )
    if result.status != existing.READY:
        return CanonicalSelectionReceipt(
            VERSION, CANONICALIZATION_VERSION, BLOCKED,
            source_database_sha256, live_artifact_sha256, None,
            result.submitted_count, result.api_request_attempt_count, result.selected_count,
        )
    try:
        digest = exact.canonical_digest(public_ids)
    except ValueError:
        return CanonicalSelectionReceipt(
            VERSION, CANONICALIZATION_VERSION, BLOCKED,
            source_database_sha256, live_artifact_sha256, None,
            result.submitted_count, result.api_request_attempt_count, result.selected_count,
        )
    return CanonicalSelectionReceipt(
        VERSION, CANONICALIZATION_VERSION, READY,
        source_database_sha256, live_artifact_sha256, digest,
        result.submitted_count, result.api_request_attempt_count, result.selected_count,
    )


def main() -> int:
    receipt = run(
        (), as_of=None, execution_authorized=False, one_shot=False,
        source_database_sha256=None, live_artifact_sha256=None,
        resolve_content_id=None, fetch_sanitized_item_payload=None, plan=None,
    )
    print(receipt.status)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
