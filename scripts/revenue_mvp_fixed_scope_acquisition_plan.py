"""Offline fixed-scope acquisition plan, not an API request or execution permit.

No network, secrets, DB access, persistence, or scheduler integration.
The plan carries only opaque IDs privately. Exact API identity resolution and
current official specification verification remain separate prerequisites.
"""
from dataclasses import dataclass, field
from hashlib import sha256
import re

from revenue_mvp_fixed_scope_refresh_review import ScopeParser, ID, utc
from datetime import datetime

BATCH_SIZE = 5


@dataclass(frozen=True)
class Plan:
    status: str
    reason_code: str
    source_sha256: str | None = None
    target_count: int = 0
    batch_count: int = 0
    batches: tuple[tuple[str, ...], ...] = field(default=(), repr=False)
    stop_on_rate_limit: bool = True
    stop_on_unconfirmed: bool = True
    automatic_retry_allowed: bool = False
    execution_allowed: bool = False
    api_calls: int = 0
    database_write_performed: bool = False
    publication_allowed: bool = False

    def summary(self):
        """Aggregate-only output; never serialize the private batch targets."""
        return {
            "status": self.status, "reason_code": self.reason_code,
            "source_sha256": self.source_sha256,
            "target_count": self.target_count, "batch_count": self.batch_count,
            "stop_on_rate_limit": self.stop_on_rate_limit,
            "stop_on_unconfirmed": self.stop_on_unconfirmed,
            "automatic_retry_allowed": self.automatic_retry_allowed,
            "execution_allowed": self.execution_allowed, "api_calls": self.api_calls,
            "database_write_performed": self.database_write_performed,
            "publication_allowed": self.publication_allowed,
        }


def build(source: bytes, expected_sha256: str) -> Plan:
    try:
        if (type(source) is not bytes or type(expected_sha256) is not str
                or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256)
                or sha256(source).hexdigest() != expected_sha256):
            return Plan("BLOCKED", "SOURCE_BINDING_INVALID")
        parser = ScopeParser()
        parser.feed(source.decode("utf-8"))
        parser.close()
        if parser.card is not None or len(parser.cards) != 100:
            return Plan("BLOCKED", "FIXED_SCOPE_INVALID")
        targets = []
        for card in parser.cards:
            if len(card["ids"]) != 1 or len(card["times"]) != 1:
                return Plan("BLOCKED", "FIXED_SCOPE_INVALID")
            value = card["ids"][0]
            if not ID.fullmatch(value) or value in targets:
                return Plan("BLOCKED", "FIXED_SCOPE_INVALID")
            utc(datetime.fromisoformat(card["times"][0].strip().replace("Z", "+00:00")))
            targets.append(value)
        # Deterministic identity order, not a public ranking or API ordering claim.
        ordered = tuple(sorted(targets))
        batches = tuple(ordered[i:i+BATCH_SIZE] for i in range(0, 100, BATCH_SIZE))
        return Plan("OFFLINE_PLAN_READY", "EXACT_RESOLUTION_AND_LIVE_APPROVAL_REQUIRED",
                    expected_sha256, 100, len(batches), batches)
    except (ValueError, TypeError, UnicodeError, AttributeError, OverflowError):
        return Plan("BLOCKED", "INPUT_INVALID")


def continuation_reason(*, outcome: str, source_unchanged: bool) -> str:
    """Pure stop decision only. No state, retry, request, or DB operation."""
    if source_unchanged is not True:
        return "STOP_SOURCE_CHANGED"
    if outcome == "RATE_LIMIT":
        return "STOP_RATE_LIMIT"
    if outcome == "NOT_AVAILABLE":
        return "STOP_SEPARATE_TAKEDOWN_REVIEW"
    if outcome != "VALID":
        return "STOP_UNCONFIRMED"
    return "STRUCTURALLY_ACCEPTED_NOT_EXECUTION_PERMISSION"
