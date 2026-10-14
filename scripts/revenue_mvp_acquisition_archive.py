"""Authenticated private archive for exact acquisition evidence.

No network, key creation/storage, database or publication operations. A trusted
32-byte-or-longer key must be supplied from a separately approved protected store.
Neither keys nor raw API responses are included in the archive or summaries.
"""
from datetime import datetime
from hashlib import sha256
import hmac
import json
from pathlib import Path

import revenue_mvp_fixed_scope_acquisition_evidence as acquisition

VERSION = "1"
SAVE_CONFIRMATION = "SAVE_PRIVATE_AUTHENTICATED_ACQUISITION_ARCHIVE"
MAX_BYTES = 1024 * 1024
ROOT = Path(__file__).resolve().parents[1]


def _key_valid(key):
    return type(key) is bytes and len(key) >= 32


def _canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()


def encode(evidence, source_bytes, candidate_bytes, *, authentication_key, evaluated_at=None):
    """Encode only a complete owned fresh receipt; returns bytes, never saves."""
    if not _key_valid(authentication_key):
        raise ValueError("ARCHIVE_AUTHENTICATION_KEY_REQUIRED")
    if not acquisition.review(evidence,source_bytes,candidate_bytes,evaluated_at=evaluated_at):
        raise ValueError("OWNED_CURRENT_ACQUISITION_EVIDENCE_REQUIRED")
    payload={"version":VERSION,"source_sha256":evidence.source_sha256,
             "candidate_sha256":evidence.candidate_sha256,
             "database_sha256":evidence.database_sha256,"api_calls":100,
             "records":[{"public_id":r.public_id,"observed_at":r.observed_at.isoformat(),
                         "exact_identity_valid":r.exact_identity_valid,
                         "affiliate_target_valid":r.affiliate_target_valid}
                        for r in evidence._records]}
    signature=hmac.new(authentication_key,_canonical(payload),"sha256").hexdigest()
    return _canonical({"payload":payload,"authentication":signature})


def _no_duplicates(pairs):
    result={}
    for key,value in pairs:
        if key in result:
            raise ValueError("ARCHIVE_DUPLICATE_FIELD")
        result[key]=value
    return result


def decode(data, source_bytes, candidate_bytes, *, expected_database_sha256,
           authentication_key, evaluated_at=None):
    """Authenticate before reconstructing a receipt. No key is read from JSON.

    Authentication means integrity under the supplied trusted key, not user
    publication approval, policy compliance, or permanent item eligibility.
    """
    if not _key_valid(authentication_key):
        raise ValueError("ARCHIVE_AUTHENTICATION_KEY_REQUIRED")
    try:
        if type(data) is not bytes or len(data)>MAX_BYTES:
            raise ValueError
        envelope=json.loads(data,object_pairs_hook=_no_duplicates)
        if type(envelope) is not dict or set(envelope)!={"payload","authentication"}:
            raise ValueError
        payload=envelope["payload"]
        if (type(payload) is not dict or set(payload)!={"version","source_sha256",
                "candidate_sha256","database_sha256","api_calls","records"}
                or payload["version"]!=VERSION
                or type(envelope["authentication"]) is not str):
            raise ValueError
        expected=hmac.new(authentication_key,_canonical(payload),"sha256").hexdigest()
        if not hmac.compare_digest(expected,envelope["authentication"]):
            raise ValueError
        if (payload["database_sha256"]!=expected_database_sha256
                or type(payload["api_calls"]) is not int or payload["api_calls"]!=100
                or type(payload["records"]) is not list or len(payload["records"])!=100):
            raise ValueError
        records=[]
        for row in payload["records"]:
            if (type(row) is not dict or set(row)!={"public_id","observed_at",
                        "exact_identity_valid","affiliate_target_valid"}
                    or row["exact_identity_valid"] is not True
                    or row["affiliate_target_valid"] is not True
                    or type(row["public_id"]) is not str
                    or type(row["observed_at"]) is not str):
                raise ValueError
            records.append(acquisition._Record(row["public_id"],
                datetime.fromisoformat(row["observed_at"]),True,True))
        value=acquisition.AcquisitionEvidence("COMPLETE_TRANSIENT_ACQUISITION_EVIDENCE",
            "AUTHENTICATED_ARCHIVE_NOT_PUBLICATION_AUTHORITY",100,
            payload["source_sha256"],payload["candidate_sha256"],
            payload["database_sha256"],tuple(records),True)
        acquisition._CAPTURES[id(value)]=value
        if not acquisition.review(value,source_bytes,candidate_bytes,evaluated_at=evaluated_at):
            acquisition._CAPTURES.pop(id(value),None)
            raise ValueError
        return value
    except (ValueError,TypeError,KeyError,UnicodeError,OverflowError):
        raise ValueError("ARCHIVE_UNVERIFIED_OR_STALE") from None


def _private_path(path):
    if not isinstance(path,Path) or not path.is_absolute():
        raise ValueError("PRIVATE_ARCHIVE_PATH_REQUIRED")
    if any(p.is_symlink() for p in (path,*path.parents)):
        raise ValueError("PRIVATE_ARCHIVE_SYMLINK_REFUSED")
    try:
        path.resolve().relative_to(ROOT.resolve())
    except ValueError:
        return
    raise ValueError("ARCHIVE_MUST_BE_OUTSIDE_REPOSITORY")


def save(evidence, source_bytes, candidate_bytes, output, *, authentication_key,
         confirmation=None, evaluated_at=None):
    """Explicit exclusive creation outside repository. Never overwrites."""
    if confirmation != SAVE_CONFIRMATION:
        raise ValueError("EXPLICIT_PRIVATE_SAVE_CONFIRMATION_REQUIRED")
    _private_path(output)
    data=encode(evidence,source_bytes,candidate_bytes,
                authentication_key=authentication_key,evaluated_at=evaluated_at)
    with output.open("xb") as handle:
        handle.write(data)
    if output.read_bytes()!=data:
        raise ValueError("ARCHIVE_WRITE_VERIFICATION_FAILED")
    return {"status":"PRIVATE_AUTHENTICATED_ARCHIVE_SAVED",
            "archive_sha256":sha256(data).hexdigest(),"record_count":100,
            "publication_allowed":False,"database_write_performed":False}


def load(path, source_bytes, candidate_bytes, *, expected_archive_sha256,
         expected_database_sha256, authentication_key, evaluated_at=None):
    _private_path(path)
    with path.open("rb") as handle:
        data=handle.read(MAX_BYTES+1)
    if len(data)>MAX_BYTES or sha256(data).hexdigest()!=expected_archive_sha256:
        raise ValueError("ARCHIVE_FILE_BINDING_INVALID")
    return decode(data,source_bytes,candidate_bytes,
                  expected_database_sha256=expected_database_sha256,
                  authentication_key=authentication_key,evaluated_at=evaluated_at)
