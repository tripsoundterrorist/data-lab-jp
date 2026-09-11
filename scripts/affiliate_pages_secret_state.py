"""Names-only, non-mutating evidence for Cloudflare Pages secrets."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import re
from typing import Any


VERSION = "0.2"
READY = "SECRET_BINDING_NAMES_READY"
BLOCKED = "BLOCKED"
FAIL_CLOSED = "FAIL_CLOSED"
REQUIRED_NAMES = frozenset({"DMM_API_ID", "DMM_AFFILIATE_ID"})
NAME_PATTERN = re.compile(r"[A-Z][A-Z0-9_]{0,63}\Z")


@dataclass(frozen=True)
class PagesSecretEvidence:
    production_environment_checked: bool
    values_not_read: bool
    observed_binding_names: tuple[str, ...]


@dataclass(frozen=True)
class PagesSecretStateResult:
    version: str
    status: str
    production_environment_checked: bool
    values_not_read: bool
    required_binding_count: int
    observed_required_binding_count: int
    verified_binding_names: tuple[str, ...]
    secret_configuration_allowed: bool
    deployment_allowed: bool
    reason_codes: tuple[str, ...]
    next_actions: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["verified_binding_names"] = list(self.verified_binding_names)
        value["reason_codes"] = list(self.reason_codes)
        value["next_actions"] = list(self.next_actions)
        return value


def current_evidence() -> PagesSecretEvidence:
    """Return the names-only result of the post-registration production check."""

    return PagesSecretEvidence(
        True,
        True,
        ("DMM_API_ID", "DMM_AFFILIATE_ID"),
    )


def assess(evidence: Any) -> PagesSecretStateResult:
    """Assess binding names only; secret values are not accepted."""

    try:
        if not isinstance(evidence, PagesSecretEvidence):
            raise ValueError("invalid evidence")
        if not isinstance(evidence.production_environment_checked, bool):
            raise ValueError("invalid check state")
        if not isinstance(evidence.values_not_read, bool):
            raise ValueError("invalid value boundary")
        names = evidence.observed_binding_names
        if (
            not isinstance(names, tuple)
            or any(not isinstance(name, str) or NAME_PATTERN.fullmatch(name) is None for name in names)
            or len(names) != len(set(names))
        ):
            raise ValueError("invalid names")

        observed_required = tuple(sorted(REQUIRED_NAMES.intersection(names)))
        reasons: list[str] = []
        actions: list[str] = []
        if not evidence.production_environment_checked:
            reasons.append("PAGES_PRODUCTION_SECRETS_NOT_CHECKED")
            actions.append("LIST_PAGES_PRODUCTION_SECRET_NAMES")
        if not evidence.values_not_read:
            reasons.append("SECRET_VALUE_BOUNDARY_NOT_VERIFIED")
            actions.append("RECHECK_NAMES_WITHOUT_READING_VALUES")
        if set(names) != REQUIRED_NAMES:
            reasons.append("REQUIRED_SECRET_BINDING_NAMES_MISSING")
            actions.append("REGISTER_REQUIRED_SECRETS_INTERACTIVELY")

        ready = not reasons
        return PagesSecretStateResult(
            VERSION,
            READY if ready else BLOCKED,
            evidence.production_environment_checked,
            evidence.values_not_read,
            len(REQUIRED_NAMES),
            len(observed_required),
            tuple(sorted(names)) if ready else (),
            False,
            False,
            tuple(reasons) or ("REQUIRED_SECRET_BINDING_NAMES_VERIFIED",),
            tuple(actions),
        )
    except Exception:
        return PagesSecretStateResult(
            VERSION,
            FAIL_CLOSED,
            False,
            False,
            len(REQUIRED_NAMES),
            0,
            (),
            False,
            False,
            ("PAGES_SECRET_STATE_INTERNAL_ERROR",),
            (),
        )


def main() -> int:
    result = assess(current_evidence())
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status in {READY, BLOCKED} else 2


if __name__ == "__main__":
    raise SystemExit(main())
