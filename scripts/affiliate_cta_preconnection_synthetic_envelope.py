"""Pure synthetic envelope policy; no transport, settings, or production path."""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
from typing import Any
from weakref import WeakKeyDictionary

import affiliate_cta_approved_context as approved
import affiliate_cta_network_disabled_wire_adapter as adapter
import affiliate_cta_offline_provider_factory as factory
import affiliate_cta_transport_capability_manifest as capability


POLICY_VERSION = "synthetic-envelope-v0.1"
MAX_BODY_BYTES = 1_048_576
MAX_URL_UTF8_BYTES = 8_192
MAX_JSON_DEPTH = 32
MAX_JSON_NODES = 4_096
MAX_NUMBER_TOKEN_BYTES = 65_536
RETRY_COUNT = 0
REDIRECT_COUNT = 0
REAL_IO_COUNT = 0
ACCEPTED = "SYNTHETIC_ENVELOPE_ACCEPTED"
BLOCKED = "SYNTHETIC_ENVELOPE_BLOCKED"
FAIL_CLOSED = "SYNTHETIC_ENVELOPE_FAIL_CLOSED"

CONFIRMED = "CONFIRMED"
PROJECT_CONTROL = "PROJECT_CONTROL"
UNCONFIRMED_BLOCKED = "UNCONFIRMED_BLOCKED"
_TOPIC_A = "OFFICIAL_MINIMUM_WIRE_EVIDENCE"
_TOPIC_B = "SYNTHETIC_ENVELOPE_CONTROL"
_TOPIC_C = "LIVE_RESPONSE_CONTRACT_UNCONFIRMED"
_EXPECTED = {
    _TOPIC_A: (CONFIRMED, "official-wire-contract-review", "72e3486589983e13389e8f3abd94c51ed7379bc89c9043e93cca17d14313ff19", "2026-09-23", "offline-minimum-wire"),
    _TOPIC_B: (PROJECT_CONTROL, "preconnection-transport-operational-evidence-review", "preconnection-synthetic-envelope-v0.1", "2026-09-23", "synthetic-fixture-only"),
}
_KNOWN_TOPICS = frozenset((*_EXPECTED, _TOPIC_C))


@dataclass(frozen=True, repr=False)
class EvidenceRequirement:
    topic_id: str
    classification: str
    source_reference: str
    source_digest: str
    source_checked_at: str
    scope: str
    superseded: bool = False

    def __repr__(self) -> str:
        return "<EvidenceRequirement>"


@dataclass(frozen=True, repr=False)
class SyntheticEnvelopeReceipt:
    status: str
    reason_code: str
    adapter_validated: bool
    owner_consumed: bool
    connection_allowed: bool = False
    activation_allowed: bool = False
    publication_allowed: bool = False
    retry_count: int = RETRY_COUNT
    redirect_count: int = REDIRECT_COUNT
    real_io_count: int = REAL_IO_COUNT

    def __repr__(self) -> str:
        return "<SyntheticEnvelopeReceipt>"


class SyntheticEnvelope:
    __slots__ = ("status", "media_type", "body", "elapsed_ms", "budget_ms", "kill_before", "kill_after", "revoked", "__weakref__")

    def __new__(cls, *_args: Any, **_kwargs: Any):
        raise TypeError("SYNTHETIC_ENVELOPE_FACTORY_REQUIRED")

    def __repr__(self) -> str:
        return "<SyntheticEnvelope>"

    def _export_forbidden(self, *_args: Any, **_kwargs: Any) -> None:
        raise TypeError("SYNTHETIC_ENVELOPE_EXPORT_FORBIDDEN")

    __reduce__ = _export_forbidden
    __reduce_ex__ = _export_forbidden
    __getstate__ = _export_forbidden
    __setstate__ = _export_forbidden


_ATTEMPTS: WeakKeyDictionary[SyntheticEnvelope, bool] = WeakKeyDictionary()


def _synthetic_envelope_for_test(*, status: Any, media_type: Any, body: Any, elapsed_ms: Any,
                                 budget_ms: Any, kill_before: Any = False, kill_after: Any = False,
                                 revoked: Any = False) -> SyntheticEnvelope | None:
    if type(status) is not int or type(media_type) is not str or type(body) is not bytes:
        return None
    if type(elapsed_ms) is not int or type(budget_ms) is not int:
        return None
    if type(kill_before) is not bool or type(kill_after) is not bool or type(revoked) is not bool:
        return None
    value = object.__new__(SyntheticEnvelope)
    for name, item in (("status", status), ("media_type", media_type), ("body", body), ("elapsed_ms", elapsed_ms),
                       ("budget_ms", budget_ms), ("kill_before", kill_before), ("kill_after", kill_after), ("revoked", revoked)):
        object.__setattr__(value, name, item)
    _ATTEMPTS[value] = False
    return value


def fixed_evidence_for_test() -> tuple[EvidenceRequirement, ...]:
    return tuple(EvidenceRequirement(topic, *values, False) for topic, values in _EXPECTED.items())


def production_policy() -> None:
    return None


def _receipt(status: str, reason: str, adapter_ok: bool = False, owner_ok: bool = False) -> SyntheticEnvelopeReceipt:
    return SyntheticEnvelopeReceipt(status, reason, adapter_ok, owner_ok)


def _evidence_valid(value: Any) -> bool:
    if type(value) is not tuple or len(value) != len(_EXPECTED):
        return False
    seen = set()
    for item in value:
        if type(item) is not EvidenceRequirement or item.topic_id in seen or item.topic_id not in _KNOWN_TOPICS:
            return False
        seen.add(item.topic_id)
        if item.superseded is True or item.topic_id == _TOPIC_C:
            return False
        expected = _EXPECTED.get(item.topic_id)
        if expected is None or (item.classification, item.source_reference, item.source_digest, item.source_checked_at, item.scope) != expected:
            return False
    return seen == set(_EXPECTED)


def _media_valid(value: Any) -> bool:
    if type(value) is not str:
        return False
    parts = [part.strip() for part in value.split(";")]
    if not parts or parts[0].lower() != "application/json":
        return False
    seen = set()
    for part in parts[1:]:
        if "=" not in part:
            return False
        name, raw = (piece.strip() for piece in part.split("=", 1))
        if name.lower() != "charset" or name.lower() in seen or raw.lower() != "utf-8":
            return False
        seen.add(name.lower())
    return True


def _decode_json(body: bytes) -> dict[str, Any] | None:
    if len(body) > MAX_BODY_BYTES:
        return None
    try:
        text = body.decode("utf-8", "strict")
        if text.startswith("\ufeff") or len(text.encode("utf-8")) > MAX_BODY_BYTES:
            return None
        def duplicate_free(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("DUPLICATE_JSON_KEY")
                result[key] = value
            return result
        def number(value: str) -> int:
            if len(value.encode("utf-8")) > MAX_NUMBER_TOKEN_BYTES:
                raise ValueError("JSON_NUMBER_TOO_LARGE")
            return int(value)
        def decimal(value: str) -> float:
            if len(value.encode("utf-8")) > MAX_NUMBER_TOKEN_BYTES:
                raise ValueError("JSON_NUMBER_TOO_LARGE")
            result = float(value)
            if not math.isfinite(result):
                raise ValueError("JSON_NUMBER_INVALID")
            return result
        parsed = json.loads(text, object_pairs_hook=duplicate_free, parse_int=number, parse_float=decimal,
                            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("JSON_CONSTANT_INVALID")))
        if type(parsed) is not dict:
            return None
        nodes = _json_structure_valid(parsed, 1)
        return parsed if nodes is not None else None
    except Exception:
        return None


def _json_structure_valid(value: Any, depth: int) -> int | None:
    if depth > MAX_JSON_DEPTH:
        return None
    if type(value) is dict:
        total = 1
        for key, item in value.items():
            if type(key) is not str:
                return None
            child = _json_structure_valid(item, depth + 1)
            if child is None:
                return None
            total += child
            if total > MAX_JSON_NODES:
                return None
        return total
    if type(value) is list:
        total = 1
        for item in value:
            child = _json_structure_valid(item, depth + 1)
            if child is None:
                return None
            total += child
            if total > MAX_JSON_NODES:
                return None
        return total
    if type(value) is str:
        if len(value.encode("utf-8")) > MAX_URL_UTF8_BYTES:
            return None
        return 1
    return 1 if type(value) in (int, float, bool, type(None)) else None


def _run_preconnection_synthetic_envelope_for_test(*, evidence: Any, envelope: Any, requested_content_id: Any,
                                                    provider: Any, public_id: Any) -> SyntheticEnvelopeReceipt:
    """One consumed synthetic attempt; it never constructs or invokes transport."""
    if type(envelope) is not SyntheticEnvelope:
        return _receipt(BLOCKED, "ENVELOPE_INVALID")
    try:
        if _ATTEMPTS.get(envelope) is not False:
            return _receipt(BLOCKED, "ATTEMPT_ALREADY_CONSUMED")
        _ATTEMPTS[envelope] = True
        if not _evidence_valid(evidence):
            return _receipt(BLOCKED, "EVIDENCE_BLOCKED")
        if not factory._synthetic_owner_ready_for_test(provider, public_id):
            return _receipt(BLOCKED, "OWNER_BLOCKED")
        if envelope.kill_before or envelope.revoked:
            return _receipt(BLOCKED, "TERMINAL_KILL_OR_REVOKE")
        if envelope.budget_ms < 1 or envelope.elapsed_ms < 0 or envelope.elapsed_ms >= envelope.budget_ms:
            return _receipt(BLOCKED, "FAKE_DEADLINE_BLOCKED")
        if envelope.status != 200:
            return _receipt(BLOCKED, "HTTP_STATUS_BLOCKED")
        if not _media_valid(envelope.media_type):
            return _receipt(BLOCKED, "MEDIA_BLOCKED")
        payload = _decode_json(envelope.body)
        if payload is None:
            return _receipt(BLOCKED, "DECODE_BLOCKED")
        observation = adapter.validate_synthetic_fixture_for_offline_harness(payload, requested_content_id)
        if type(observation) is not adapter.ValidatedSyntheticFixtureObservation:
            return _receipt(BLOCKED, "SEMANTIC_VALIDATION_BLOCKED")
        consumed = factory._consume_validated_synthetic_for_test(provider, public_id, observation)
        if type(consumed) is not approved._InternalObservation:
            return _receipt(FAIL_CLOSED, "OWNER_CONSUMPTION_BLOCKED", True)
        if envelope.kill_after or envelope.revoked or not factory._synthetic_owner_ready_for_test(provider, public_id):
            return _receipt(BLOCKED, "FINAL_LEASE_BLOCKED", True, True)
        return _receipt(ACCEPTED, "SYNTHETIC_ONLY", True, True)
    except Exception:
        return _receipt(FAIL_CLOSED, "INTERNAL_FAILURE")


OFFICIAL_WIRE_CONTRACT_VERSION = capability.OFFICIAL_WIRE_CONTRACT_VERSION

__all__ = ["ACCEPTED", "BLOCKED", "EvidenceRequirement", "FAIL_CLOSED", "OFFICIAL_WIRE_CONTRACT_VERSION",
           "POLICY_VERSION", "SyntheticEnvelopeReceipt", "fixed_evidence_for_test", "production_policy"]
