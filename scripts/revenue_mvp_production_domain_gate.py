"""URL-free operator evidence gate for the DMM approved production site."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Any


VERSION = "0.1"
READY = "READY_FOR_CONDITION_REVIEW"
PENDING = "PENDING_OPERATOR_CONFIRMATION"
FAIL_CLOSED = "FAIL_CLOSED"


@dataclass(frozen=True)
class DomainApprovalEvidence:
    approved_site_confirmed: bool
    production_domain_matches_approved_site: bool
    url_change_application_pending: bool


@dataclass(frozen=True)
class DomainApprovalResult:
    version: str
    status: str
    condition_verified: bool
    gate_unlock_allowed: bool
    production_change_allowed: bool
    reason_codes: tuple[str, ...]
    next_actions: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        value["next_actions"] = list(self.next_actions)
        return value


def current_evidence() -> DomainApprovalEvidence:
    """Return the sanitized operator-confirmed production-domain evidence."""

    return DomainApprovalEvidence(True, True, False)


def assess(value: Any) -> DomainApprovalResult:
    try:
        if not isinstance(value, DomainApprovalEvidence) or any(
            not isinstance(item, bool) for item in asdict(value).values()
        ):
            raise ValueError("invalid evidence")
        reasons: list[str] = []
        actions: list[str] = []
        if not value.approved_site_confirmed:
            reasons.append("APPROVED_SITE_NOT_CONFIRMED")
            actions.append("CONFIRM_DMM_APPROVED_SITE_IN_ACCOUNT")
        if not value.production_domain_matches_approved_site:
            reasons.append("PRODUCTION_DOMAIN_MATCH_NOT_CONFIRMED")
            actions.append("CONFIRM_PRODUCTION_DOMAIN_MATCH")
        if value.url_change_application_pending:
            reasons.append("URL_CHANGE_APPLICATION_PENDING")
            actions.append("WAIT_FOR_URL_CHANGE_APPLICATION")
        verified = not reasons
        return DomainApprovalResult(
            VERSION, READY if verified else PENDING, verified, False, False,
            tuple(reasons) or ("PRODUCTION_DOMAIN_CONDITION_EVIDENCED",),
            tuple(actions),
        )
    except Exception:
        return DomainApprovalResult(
            VERSION, FAIL_CLOSED, False, False, False,
            ("DOMAIN_APPROVAL_GATE_INTERNAL_ERROR",), (),
        )


def main() -> int:
    result = assess(current_evidence())
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status in {READY, PENDING} else 2


if __name__ == "__main__":
    raise SystemExit(main())
