"""Process-owned, sanitized acquisition evidence. No durable storage or release.

Only explicit capture calls HTTP; neither review nor serialization calls it.
Serialized summaries are NOT trusted; authenticated private archives require
the separate archive verifier and an independently supplied protected key.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from hashlib import sha256
from weakref import WeakValueDictionary

import revenue_mvp_fixed_scope_first_five as reader
import revenue_mvp_price_display_transition as display

CONFIRMATION = "READ_ONLY_FIXED_SCOPE_HUNDRED_WITH_TRANSIENT_EVIDENCE"
_CAPTURES = WeakValueDictionary()


@dataclass(frozen=True)
class _Record:
    public_id: str
    observed_at: datetime
    exact_identity_valid: bool
    affiliate_target_valid: bool


@dataclass(frozen=True, eq=False)
class AcquisitionEvidence:
    status: str
    reason_code: str
    api_calls: int
    source_sha256: str
    candidate_sha256: str
    database_sha256: str
    _records: tuple = field(default=(), repr=False)
    _archive_authenticated: bool = field(default=False, repr=False)

    def summary(self):
        return {"status":self.status,"reason_code":self.reason_code,
                "api_calls":self.api_calls,"validated_count":len(self._records),
                "source_sha256":self.source_sha256,
                "candidate_sha256":self.candidate_sha256,
                "earliest_observed_at":min((r.observed_at.isoformat() for r in self._records),default=None),
                "latest_observed_at":max((r.observed_at.isoformat() for r in self._records),default=None),
                "raw_payload_persisted":False,"database_write_performed":False,
                "publication_allowed":False,"durable_receipt_available":False,
                "authenticated_archive_loaded":self._archive_authenticated}


def capture(source, database, environment, candidate_bytes, *,
            expected_source_sha256, expected_database_sha256,
            execute=False, confirmation=None):
    """Exactly 100 fixed identities; fail whole capture on any unconfirmed item.

    No caller-supplied responses, transport, resolver or timestamps accepted.
    Tests mock dependencies, not a production trust-injection interface.
    """
    calls = 0
    candidate_hash = ""
    source_hash = ""
    def result(status, reason, records=()):
        value = AcquisitionEvidence(status,reason,calls,source_hash,
                                    candidate_hash,expected_database_sha256,records)
        if status == "COMPLETE_TRANSIENT_ACQUISITION_EVIDENCE":
            _CAPTURES[id(value)] = value
        return value
    try:
        candidate_hash = sha256(display.canonical(candidate_bytes)).hexdigest()
        source_hash = sha256(display.canonical(source.read_bytes())).hexdigest()
        if (candidate_hash != display.CANDIDATE
                or source_hash != display.BASELINE
                or not reader.bound(source,database,expected_source_sha256,expected_database_sha256)):
            return result("BLOCKED","INPUT_BINDING_INVALID")
        plan = reader.planner.build(source.read_bytes(),expected_source_sha256)
        if plan.status != "OFFLINE_PLAN_READY":
            return result("BLOCKED","FIXED_SCOPE_INVALID")
        selected = tuple(x for b in plan.batches for x in b)
        if len(selected) != 100 or len(set(selected)) != 100:
            return result("BLOCKED","FIXED_SCOPE_INVALID")
        if execute is not True:
            return result("OFFLINE_EVIDENCE_CAPTURE_READY","EXPLICIT_LIVE_CONFIRMATION_REQUIRED")
        if confirmation != CONFIRMATION:
            return result("BLOCKED","LIVE_CONFIRMATION_REQUIRED")
        if not environment.is_file() or environment.is_symlink():
            return result("BLOCKED","ENVIRONMENT_BOUNDARY_INVALID")
        resolved=[]
        for identity in selected:
            if not reader.bound(source,database,expected_source_sha256,expected_database_sha256):
                return result("BLOCKED","INPUT_CHANGED")
            cid = reader.connector.resolve_content_id(database,identity)
            if (type(cid) is not str or not reader.connector.CONTENT_ID.fullmatch(cid)
                    or reader.connector._public_item_id("FANZA","digital","videoa",cid) != identity):
                return result("BLOCKED","EXACT_IDENTITY_UNRESOLVED")
            resolved.append((identity,cid))
        records=[]
        for identity,cid in resolved:
            if calls:
                reader.time.sleep(1.0)
            if not reader.bound(source,database,expected_source_sha256,expected_database_sha256):
                return result("BLOCKED","INPUT_CHANGED")
            calls += 1
            payload = reader.fetch_exact(content_id=cid,env_path=environment)
            stamp = datetime.now(timezone.utc)
            decoded = reader.decoder.decode(target_public_id=identity,resolved_content_id=cid,
                payload=payload,http_status=200,observed_at=stamp,evaluated_at=stamp)
            del payload
            if decoded.status != "STRUCTURAL_OBSERVATION_READY":
                return result("BLOCKED",decoded.reason_code)
            records.append(_Record(identity,stamp,True,True))
            del decoded
        if not reader.bound(source,database,expected_source_sha256,expected_database_sha256):
            return result("BLOCKED","INPUT_CHANGED")
        return result("COMPLETE_TRANSIENT_ACQUISITION_EVIDENCE",
                      "NO_PERSISTENCE_OR_PUBLICATION_AUTHORITY",tuple(records))
    except Exception:
        return result("BLOCKED","ACQUISITION_UNCONFIRMED_STOP")


def review(evidence, source_bytes, candidate_bytes, *, evaluated_at=None):
    """Validate owned identity, exact coverage/bindings and per-item <=24h age."""
    try:
        if (type(evidence) is not AcquisitionEvidence
                or _CAPTURES.get(id(evidence)) is not evidence
                or evidence.status != "COMPLETE_TRANSIENT_ACQUISITION_EVIDENCE"):
            return False
        raw_hash = sha256(source_bytes).hexdigest()
        source_hash = sha256(display.canonical(source_bytes)).hexdigest()
        candidate_hash = sha256(display.canonical(candidate_bytes)).hexdigest()
        if (source_hash != evidence.source_sha256 or candidate_hash != evidence.candidate_sha256
                or candidate_hash != display.CANDIDATE or source_hash != display.BASELINE):
            return False
        plan=reader.planner.build(source_bytes,raw_hash)
        expected={x for b in plan.batches for x in b} if plan.status == "OFFLINE_PLAN_READY" else set()
        now = evaluated_at or datetime.now(timezone.utc)
        records = evidence._records
        return (len(expected) == 100 and evidence.api_calls == 100 and len(records) == 100
            and {r.public_id for r in records} == expected
            and all(r.exact_identity_valid is True and r.affiliate_target_valid is True
                    and timedelta(0) <= now-r.observed_at <= timedelta(hours=24) for r in records))
    except (TypeError,ValueError,AttributeError,OverflowError):
        return False
