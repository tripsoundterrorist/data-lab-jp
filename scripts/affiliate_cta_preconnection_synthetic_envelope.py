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
PROJECT_CONTROL_VERSION = "preconnection-synthetic-envelope-v0.1"
PROJECT_CONTROL_SOURCE_DIGEST = "bd62fd2d844be9be0b3e7835a69d896be89eff266492a4293c91b070cfeea425"
MAX_BODY_BYTES = 1_048_576
MAX_URL_UTF8_BYTES = 8_192
MAX_JSON_DEPTH = 32
MAX_JSON_NODES = 4_096
MAX_STRING_TOKEN_BYTES = 65_536  # raw UTF-8 bytes, including escapes; keys included
MAX_NUMBER_TOKEN_CHARS = 64  # numeric grammar characters before conversion
MAX_MEDIA_TYPE_CHARS = 128
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
    _TOPIC_A: (CONFIRMED, "official-wire-contract-review", "72e3486589983e13389e8f3abd94c51ed7379bc89c9043e93cca17d14313ff19", "2026-09-23", "offline-minimum-wire", ""),
    _TOPIC_B: (PROJECT_CONTROL, "preconnection-transport-operational-evidence-review", PROJECT_CONTROL_SOURCE_DIGEST, "2026-09-23", "synthetic-fixture-only", PROJECT_CONTROL_VERSION),
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
    project_control_version: str = ""

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
    __slots__ = ("__weakref__",)

    def __new__(cls, *_args: Any, **_kwargs: Any):
        raise TypeError("SYNTHETIC_ENVELOPE_FACTORY_REQUIRED")

    def __repr__(self) -> str:
        return "<SyntheticEnvelope>"

    def __setattr__(self, _name: str, _value: Any) -> None:
        raise AttributeError("SYNTHETIC_ENVELOPE_IMMUTABLE")

    def _export_forbidden(self, *_args: Any, **_kwargs: Any) -> None:
        raise TypeError("SYNTHETIC_ENVELOPE_EXPORT_FORBIDDEN")

    __reduce__ = _export_forbidden
    __reduce_ex__ = _export_forbidden
    __getstate__ = _export_forbidden
    __setstate__ = _export_forbidden
    __copy__ = _export_forbidden
    __deepcopy__ = _export_forbidden


@dataclass(frozen=True, repr=False)
class _IssuedEnvelope:
    status: int
    media_type: str
    body: bytes
    elapsed_ms: int
    budget_ms: int
    kill_before: bool
    kill_after: bool
    revoked: bool


_ATTEMPTS: WeakKeyDictionary[SyntheticEnvelope, tuple[_IssuedEnvelope, bool]] = WeakKeyDictionary()


class ValidatedSyntaxHandoff:
    """Opaque one-use proof issued only after this module's bounded syntax gate."""

    __slots__ = ("__weakref__",)

    def __new__(cls, *_args: Any, **_kwargs: Any):
        raise TypeError("SYNTAX_HANDOFF_ISSUER_REQUIRED")

    def __setattr__(self, _name: str, _value: Any) -> None:
        raise AttributeError("SYNTAX_HANDOFF_IMMUTABLE")

    def __repr__(self) -> str:
        return "<ValidatedSyntaxHandoff>"

    def _export_forbidden(self, *_args: Any, **_kwargs: Any) -> None:
        raise TypeError("SYNTAX_HANDOFF_EXPORT_FORBIDDEN")

    __reduce__ = _export_forbidden
    __reduce_ex__ = _export_forbidden
    __getstate__ = _export_forbidden
    __setstate__ = _export_forbidden
    __copy__ = _export_forbidden
    __deepcopy__ = _export_forbidden


@dataclass(repr=False)
class _SyntaxState:
    payload: dict[str, Any]
    provider: Any
    public_id: str
    snapshot: _IssuedEnvelope
    consumed: bool = False


_SYNTAX_HANDOFFS: WeakKeyDictionary[ValidatedSyntaxHandoff, _SyntaxState] = WeakKeyDictionary()


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
    _ATTEMPTS[value] = (_IssuedEnvelope(status, media_type, body, elapsed_ms, budget_ms,
                                        kill_before, kill_after, revoked), False)
    return value


def fixed_evidence_for_test() -> tuple[EvidenceRequirement, ...]:
    return tuple(EvidenceRequirement(topic, *values[:5], False, values[5]) for topic, values in _EXPECTED.items())


def production_policy() -> None:
    return None


def _receipt(status: str, reason: str, adapter_ok: bool = False, owner_ok: bool = False) -> SyntheticEnvelopeReceipt:
    return SyntheticEnvelopeReceipt(status, reason, adapter_ok, owner_ok)


def _evidence_valid(value: Any) -> bool:
    """This A/B offline subset never resolves the omitted C live topic."""
    if type(value) is not tuple or len(value) != len(_EXPECTED):
        return False
    seen = set()
    for item in value:
        if type(item) is not EvidenceRequirement:
            return False
        fields = (item.topic_id, item.classification, item.source_reference,
                  item.source_digest, item.source_checked_at, item.scope, item.project_control_version)
        if any(type(field) is not str for field in fields) or type(item.superseded) is not bool:
            return False
        if item.superseded is not False or item.topic_id in seen or item.topic_id not in _KNOWN_TOPICS:
            return False
        seen.add(item.topic_id)
        if item.topic_id == _TOPIC_C:
            return False
        expected = _EXPECTED.get(item.topic_id)
        if expected is None or fields[1:] != expected:
            return False
    return seen == set(_EXPECTED)


def _media_valid(value: Any) -> bool:
    if type(value) is not str or len(value) > MAX_MEDIA_TYPE_CHARS:
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
        if text.startswith("\ufeff") or not _scan_json_bounds(text):
            return None
        def duplicate_free(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("DUPLICATE_JSON_KEY")
                result[key] = value
            return result
        def decimal(value: str) -> float:
            result = float(value)
            if not math.isfinite(result):
                raise ValueError("JSON_NUMBER_INVALID")
            return result
        parsed = json.loads(text, object_pairs_hook=duplicate_free, parse_float=decimal,
                            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("JSON_CONSTANT_INVALID")))
        return parsed if type(parsed) is dict else None
    except Exception:
        return None


def _scan_json_bounds(text: str) -> bool:
    """Bound grammar before tree allocation. Root/container/scalar values are nodes; keys are not.

    Every string token (key or value) has a 64 KiB raw UTF-8 cap. The
    affiliateURL value also has an 8192 byte decoded UTF-8 cap. These are
    synthetic project controls, not provider limits or product validation.
    """
    length = len(text)
    position = 0
    nodes = 0

    def whitespace() -> None:
        nonlocal position
        while position < length and text[position] in " \t\r\n":
            position += 1

    def string(*, url_value: bool = False) -> str:
        nonlocal position
        if position >= length or text[position] != '"':
            raise ValueError("STRING_EXPECTED")
        start = position
        raw_bytes = 1
        position += 1
        while position < length:
            char = text[position]
            if char == '"':
                position += 1
                raw_bytes += 1
                if raw_bytes > MAX_STRING_TOKEN_BYTES:
                    raise ValueError("STRING_TOKEN_LIMIT")
                token = text[start:position]
                decoded = json.loads(token)
                if url_value and len(decoded.encode("utf-8")) > MAX_URL_UTF8_BYTES:
                    raise ValueError("URL_BYTE_LIMIT")
                return decoded
            if char == "\\":
                raw_bytes += 1
                position += 1
                if position >= length:
                    raise ValueError("ESCAPE_INVALID")
                escape = text[position]
                if escape == "u":
                    if position + 4 >= length or any(digit not in "0123456789abcdefABCDEF" for digit in text[position + 1:position + 5]):
                        raise ValueError("UNICODE_ESCAPE_INVALID")
                    position += 4
                    raw_bytes += 5
                elif escape not in '"\\/bfnrt':
                    raise ValueError("ESCAPE_INVALID")
                else:
                    raw_bytes += 1
            elif ord(char) < 0x20:
                raise ValueError("CONTROL_INVALID")
            else:
                raw_bytes += len(char.encode("utf-8"))
            position += 1
            if raw_bytes > MAX_STRING_TOKEN_BYTES:
                raise ValueError("STRING_TOKEN_LIMIT")
        raise ValueError("STRING_UNCLOSED")

    def value(depth: int, *, url_value: bool = False) -> None:
        nonlocal position, nodes
        nodes += 1
        if depth > MAX_JSON_DEPTH or nodes > MAX_JSON_NODES or position >= length:
            raise ValueError("STRUCTURE_LIMIT")
        char = text[position]
        if char == "{":
            position += 1
            whitespace()
            if position < length and text[position] == "}":
                position += 1
                return
            while True:
                key = string()
                whitespace()
                if position >= length or text[position] != ":":
                    raise ValueError("COLON_EXPECTED")
                position += 1
                whitespace()
                value(depth + 1, url_value=key == "affiliateURL")
                whitespace()
                if position < length and text[position] == "}":
                    position += 1
                    return
                if position >= length or text[position] != ",":
                    raise ValueError("OBJECT_DELIMITER")
                position += 1
                whitespace()
        elif char == "[":
            position += 1
            whitespace()
            if position < length and text[position] == "]":
                position += 1
                return
            while True:
                value(depth + 1)
                whitespace()
                if position < length and text[position] == "]":
                    position += 1
                    return
                if position >= length or text[position] != ",":
                    raise ValueError("ARRAY_DELIMITER")
                position += 1
                whitespace()
        elif char == '"':
            string(url_value=url_value)
        elif char in "-0123456789":
            start = position
            if char == "-":
                position += 1
            if position >= length:
                raise ValueError("NUMBER_INVALID")
            if text[position] == "0":
                position += 1
            elif text[position] in "123456789":
                while position < length and text[position] in "0123456789":
                    position += 1
            else:
                raise ValueError("NUMBER_INVALID")
            if position < length and text[position] == ".":
                position += 1
                if position >= length or text[position] not in "0123456789":
                    raise ValueError("NUMBER_INVALID")
                while position < length and text[position] in "0123456789":
                    position += 1
            if position < length and text[position] in "eE":
                position += 1
                if position < length and text[position] in "+-":
                    position += 1
                if position >= length or text[position] not in "0123456789":
                    raise ValueError("NUMBER_INVALID")
                while position < length and text[position] in "0123456789":
                    position += 1
            if position - start > MAX_NUMBER_TOKEN_CHARS:
                raise ValueError("NUMBER_TOKEN_LIMIT")
        else:
            for literal in ("true", "false", "null"):
                if text.startswith(literal, position):
                    position += len(literal)
                    return
            raise ValueError("VALUE_INVALID")

    try:
        whitespace()
        value(1)
        whitespace()
        return position == length
    except (RecursionError, ValueError, UnicodeError):
        return False


def _run_preconnection_synthetic_envelope_for_test(*, evidence: Any, envelope: Any, requested_content_id: Any,
                                                    provider: Any, public_id: Any,
                                                    _syntax_only: bool = False) -> SyntheticEnvelopeReceipt | ValidatedSyntaxHandoff:
    """One consumed synthetic attempt; it never constructs or invokes transport."""
    if type(envelope) is not SyntheticEnvelope:
        return _receipt(BLOCKED, "ENVELOPE_INVALID")
    owner_checked = False

    def terminal(status: str, reason: str, adapter_ok: bool = False, owner_ok: bool = False) -> SyntheticEnvelopeReceipt:
        if owner_checked:
            factory._stop_synthetic_owner_for_test(provider)
        return _receipt(status, reason, adapter_ok, owner_ok)

    try:
        entry = _ATTEMPTS.get(envelope)
        if type(entry) is not tuple or len(entry) != 2 or entry[1] is not False:
            factory._stop_synthetic_owner_for_test(provider)
            return _receipt(BLOCKED, "ATTEMPT_ALREADY_CONSUMED")
        snapshot = entry[0]
        _ATTEMPTS[envelope] = (snapshot, True)
        if not _evidence_valid(evidence):
            factory._stop_synthetic_owner_for_test(provider)
            return _receipt(BLOCKED, "EVIDENCE_BLOCKED")
        if not factory._synthetic_owner_ready_for_test(provider, public_id):
            return _receipt(BLOCKED, "OWNER_BLOCKED")
        owner_checked = True
        if type(snapshot) is not _IssuedEnvelope or any((
            type(snapshot.status) is not int,
            type(snapshot.elapsed_ms) is not int,
            type(snapshot.budget_ms) is not int,
            type(snapshot.kill_before) is not bool,
            type(snapshot.kill_after) is not bool,
            type(snapshot.revoked) is not bool,
        )):
            return terminal(FAIL_CLOSED, "ENVELOPE_STATE_INVALID")
        if snapshot.kill_before or snapshot.revoked:
            return terminal(BLOCKED, "TERMINAL_KILL_OR_REVOKE")
        if snapshot.budget_ms < 1 or snapshot.elapsed_ms < 0 or snapshot.elapsed_ms >= snapshot.budget_ms:
            return terminal(BLOCKED, "FAKE_DEADLINE_BLOCKED")
        if snapshot.status != 200:
            return terminal(BLOCKED, "HTTP_STATUS_BLOCKED")
        if type(snapshot.media_type) is not str:
            return terminal(FAIL_CLOSED, "ENVELOPE_STATE_INVALID")
        if not _media_valid(snapshot.media_type):
            return terminal(BLOCKED, "MEDIA_BLOCKED")
        if type(snapshot.body) is not bytes:
            return terminal(FAIL_CLOSED, "ENVELOPE_STATE_INVALID")
        payload = _decode_json(snapshot.body)
        if payload is None:
            return terminal(BLOCKED, "DECODE_BLOCKED")
        if _syntax_only is True:
            handoff = object.__new__(ValidatedSyntaxHandoff)
            _SYNTAX_HANDOFFS[handoff] = _SyntaxState(payload, provider, public_id, snapshot)
            return handoff
        observation = adapter.validate_synthetic_fixture_for_offline_harness(payload, requested_content_id)
        if type(observation) is not adapter.ValidatedSyntheticFixtureObservation:
            return terminal(BLOCKED, "SEMANTIC_VALIDATION_BLOCKED")
        consumed = factory._consume_validated_synthetic_for_test(provider, public_id, observation)
        if type(consumed) is not approved._InternalObservation:
            return terminal(FAIL_CLOSED, "OWNER_CONSUMPTION_BLOCKED", True)
        if snapshot.kill_after or snapshot.revoked or not factory._synthetic_owner_ready_for_test(provider, public_id):
            return terminal(BLOCKED, "FINAL_LEASE_BLOCKED", True, True)
        return _receipt(ACCEPTED, "SYNTHETIC_ONLY", True, True)
    except Exception:
        return terminal(FAIL_CLOSED, "INTERNAL_FAILURE")


def issue_syntax_handoff_for_test(*, evidence: Any, envelope: Any, provider: Any,
                                  public_id: Any) -> ValidatedSyntaxHandoff | None:
    """Issue only after the same fake owner, deadline, media and bounded syntax gates."""
    result = _run_preconnection_synthetic_envelope_for_test(
        evidence=evidence, envelope=envelope, requested_content_id=None,
        provider=provider, public_id=public_id, _syntax_only=True,
    )
    return result if type(result) is ValidatedSyntaxHandoff else None


def consume_syntax_handoff_for_projection_for_test(*, handoff: Any, provider: Any,
                                                    public_id: Any, dispositions: Any,
                                                    requested_content_id: Any) -> Any:
    """Pass one owner-held mapping to the fixed projection stage; never export it."""
    import affiliate_cta_offline_wire_projection_redaction as projection

    if type(handoff) is not ValidatedSyntaxHandoff:
        return None
    trusted_lifecycle = False
    try:
        state = _SYNTAX_HANDOFFS.get(handoff)
        if (type(state) is not _SyntaxState or type(state.public_id) is not str
                or type(state.consumed) is not bool or type(public_id) is not str):
            return None
        if state.provider is not provider or state.public_id != public_id:
            return None
        # Only a proven matching issued lifecycle may terminally stop this owner.
        trusted_lifecycle = True
        if state.consumed is True:
            factory._stop_synthetic_owner_for_test(provider)
            return None
        if not factory._synthetic_owner_ready_for_test(provider, public_id):
            return None
        state.consumed = True
        receipt = projection._process_syntax_validated_payload_for_test(
            payload=state.payload, dispositions=dispositions,
            requested_content_id=requested_content_id, provider=provider, public_id=public_id,
        )
        if type(receipt) is not projection.ProjectionReceipt or receipt.status != projection.ACCEPTED:
            factory._stop_synthetic_owner_for_test(provider)
            return receipt if type(receipt) is projection.ProjectionReceipt else None
        if (state.snapshot.kill_after or state.snapshot.revoked
                or not factory._synthetic_owner_ready_for_test(provider, public_id)):
            factory._stop_synthetic_owner_for_test(provider)
            return projection._receipt(projection.BLOCKED, "FINAL_LEASE_BLOCKED",
                                       kept=receipt.kept_field_count,
                                       adapter_ok=True, owner_ok=True)
        return receipt
    except Exception:
        if trusted_lifecycle:
            factory._stop_synthetic_owner_for_test(provider)
        return None


OFFICIAL_WIRE_CONTRACT_VERSION = capability.OFFICIAL_WIRE_CONTRACT_VERSION

__all__ = ["ACCEPTED", "BLOCKED", "EvidenceRequirement", "FAIL_CLOSED", "OFFICIAL_WIRE_CONTRACT_VERSION",
           "POLICY_VERSION", "SyntheticEnvelopeReceipt", "fixed_evidence_for_test", "production_policy"]
