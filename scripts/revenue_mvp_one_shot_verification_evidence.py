"""Validate the sanitized one-shot DMM API verification receipt."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any


VERSION = "0.1"
READY = "ONE_SHOT_VERIFICATION_EVIDENCE_READY"
BLOCKED = "ONE_SHOT_VERIFICATION_EVIDENCE_BLOCKED"
EVIDENCE = (Path(__file__).resolve().parents[1] / "runtime/evidence/"
            "revenue-mvp-one-shot-api-verification-20260925.json")


@dataclass(frozen=True)
class OneShotVerificationEvidence:
    version: str
    status: str
    request_verified: bool
    api_calls: int
    retry_performed: bool
    writes_performed: bool
    gate_unlock_allowed: bool
    production_activation_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def assess_evidence() -> OneShotVerificationEvidence:
    try:
        value = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        expected = {
            "evidence_version", "executed_on", "execution_mode", "status",
            "request_attempt_limit", "api_calls", "retry_performed",
            "api_result_status_200", "result_count_positive", "items_returned",
            "title_present", "current_price_present", "release_date_present",
            "review_present", "affiliate_url_present",
            "database_write_performed", "artifact_write_performed",
            "publication_performed", "identifiers_stored", "urls_stored",
            "secret_values_stored", "gate_unlock_allowed",
            "production_activation_allowed",
        }
        valid = (
            type(value) is dict and set(value) == expected
            and value["evidence_version"] == VERSION
            and value["executed_on"] == "2026-09-25"
            and value["execution_mode"] == "MANUAL_ONE_SHOT_READ_ONLY"
            and value["status"] == "SUCCESS"
            and type(value["request_attempt_limit"]) is int
            and value["request_attempt_limit"] == 1
            and type(value["api_calls"]) is int
            and value["api_calls"] == 1
            and value["retry_performed"] is False
            and value["api_result_status_200"] is True
            and value["result_count_positive"] is True
            and type(value["items_returned"]) is int
            and value["items_returned"] == 1
            and value["title_present"] is True
            and value["current_price_present"] is True
            and value["release_date_present"] is True
            and value["review_present"] is False
            and value["affiliate_url_present"] is True
            and value["database_write_performed"] is False
            and value["artifact_write_performed"] is False
            and value["publication_performed"] is False
            and value["identifiers_stored"] is False
            and value["urls_stored"] is False
            and value["secret_values_stored"] is False
            and value["gate_unlock_allowed"] is False
            and value["production_activation_allowed"] is False
        )
        if not valid:
            raise ValueError("one-shot evidence mismatch")
        return OneShotVerificationEvidence(
            VERSION, READY, True, 1, False, False, False, False,
            ("ONE_SHOT_REQUEST_SUCCEEDED", "NO_RETRY_OR_WRITE_PERFORMED",
             "ACTIVATION_REMAINS_CLOSED"),
        )
    except Exception:
        return OneShotVerificationEvidence(
            VERSION, BLOCKED, False, 0, False, False, False, False,
            ("ONE_SHOT_VERIFICATION_EVIDENCE_INVALID",),
        )


if __name__ == "__main__":
    print(json.dumps(assess_evidence().to_dict(), ensure_ascii=False,
                     sort_keys=True))
