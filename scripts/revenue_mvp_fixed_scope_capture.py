"""Explicit five-item capture and in-memory authenticated format; no storage.

No CLI, DPAPI, key generation, database writes, scheduler or release connection.
Only capture(execute=True, confirmation=...) can call the existing transport.
Tests patch that dependency; operational callers cannot supply a fetch callback.
Authentication proves integrity under a separately trusted key, not freshness
forever, current availability, user approval or publication permission.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import hmac
import json
from pathlib import Path
from weakref import WeakValueDictionary

import revenue_mvp_fixed_scope_first_five as reader
import revenue_mvp_fixed_scope_handoff as handoff
from revenue_mvp_fixed_scope_refresh_review import Observation

DOMAIN = b'DATA-LAB-fixed-five-price-image-archive-v1\0'
VERSION = 'FIXED_FIVE_PRICE_IMAGE_1'
MAX_BYTES = 128 * 1024
_OWNED = WeakValueDictionary()


def confirmation_for(batch_index):
    if type(batch_index) is not int or not 0 <= batch_index < 20:
        raise ValueError('BATCH_INVALID')
    return f'CAPTURE_FIXED_FIVE_{batch_index:02d}_NO_WRITE'


@dataclass(frozen=True, eq=False)
class Capture:
    api_calls: int
    _data: bytes = field(repr=False)

    def summary(self):
        return dict(status='FIVE_ITEM_CAPTURE_READY', api_calls=self.api_calls,
                    record_count=5, raw_payload_persisted=False,
                    output_written=False, database_write_performed=False,
                    publication_allowed=False)


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


def _issue(data):
    result = Capture(5, data)
    _OWNED[id(result)] = result
    return result


def capture(source, database, environment, *, expected_source_sha256,
            expected_database_sha256, batch_index=0, execute=False, confirmation=None):
    calls = 0
    def blocked(reason):
        return dict(status='BLOCKED', reason_code=reason, api_calls=calls,
                    database_write_performed=False, output_written=False,
                    publication_allowed=False), None
    try:
        required = confirmation_for(batch_index)
        if execute is not True or confirmation != required:
            return blocked('EXPLICIT_CAPTURE_CONFIRMATION_REQUIRED')
        if (any(not isinstance(p, Path) for p in (source, database, environment))
                or any(p.is_symlink() for p in (source, database, environment))
                or any(parent.is_symlink() for p in (source, database, environment) for parent in p.parents)
                or not environment.is_file()
                or not reader.bound(source, database, expected_source_sha256, expected_database_sha256)):
            return blocked('INPUT_BINDING_INVALID')
        source_bytes = source.read_bytes()
        plan = reader.planner.build(source_bytes, expected_source_sha256)
        if plan.status != 'OFFLINE_PLAN_READY':
            return blocked('FIXED_SCOPE_INVALID')
        resolved = []
        for identity in plan.batches[batch_index]:
            if not reader.bound(source, database, expected_source_sha256, expected_database_sha256):
                return blocked('INPUT_CHANGED')
            cid = reader.connector.resolve_content_id(database, identity)
            if (type(cid) is not str or not reader.connector.CONTENT_ID.fullmatch(cid)
                    or reader.connector._public_item_id('FANZA','digital','videoa',cid) != identity):
                return blocked('EXACT_IDENTITY_UNRESOLVED')
            resolved.append((identity, cid))
        if len(resolved) != 5 or len({cid for _, cid in resolved}) != 5:
            return blocked('EXACT_FIVE_REQUIRED')
        decoded = []
        for identity, cid in resolved:
            if calls:
                reader.time.sleep(1.0)
            if not reader.bound(source, database, expected_source_sha256, expected_database_sha256):
                return blocked('INPUT_CHANGED')
            stamp = datetime.now(timezone.utc)
            calls += 1
            payload = reader.fetch_exact(content_id=cid, env_path=environment)
            result = reader.decoder.decode(target_public_id=identity, resolved_content_id=cid,
                payload=payload, http_status=200, observed_at=stamp,
                evaluated_at=datetime.now(timezone.utc))
            del payload
            if result.status != 'STRUCTURAL_OBSERVATION_READY':
                return blocked(result.reason_code)
            decoded.append(result)
        if not reader.bound(source, database, expected_source_sha256, expected_database_sha256):
            return blocked('INPUT_CHANGED')
        receipt, data = handoff.build(source_bytes, expected_source_sha256,
            expected_database_sha256, tuple(decoded), batch_index=batch_index,
            evaluated_at=datetime.now(timezone.utc))
        if data is None:
            return blocked(receipt['reason_code'])
        result = _issue(data)
        return result.summary(), result
    except Exception:
        return blocked('CAPTURE_UNCONFIRMED_STOP')


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('DUPLICATE_FIELD')
        result[key] = value
    return result


def _validate(data, source_bytes, expected_database_sha256, batch_index, evaluated_at):
    if type(data) is not bytes or len(data) > MAX_BYTES:
        raise ValueError('PAYLOAD_INVALID')
    value = json.loads(data, object_pairs_hook=_unique)
    if (type(value) is not dict or set(value) != {'version','source_sha256','database_sha256',
            'batch_index','trusted_acquisition_confirmed','records'}
            or value['version'] != 'OFFLINE_PROTOTYPE_1'
            or value['trusted_acquisition_confirmed'] is not False
            or type(value['batch_index']) is not int or value['batch_index'] != batch_index
            or value['database_sha256'] != expected_database_sha256
            or type(value['records']) is not list or len(value['records']) != 5):
        raise ValueError('PAYLOAD_BINDING_INVALID')
    decoded = []
    for row in value['records']:
        if type(row) is not dict or set(row) != {'public_id','price','price_is_lower_bound','image_url','observed_at'}:
            raise ValueError('RECORD_SCHEMA_INVALID')
        stamp = datetime.fromisoformat(row['observed_at'])
        decoded.append(reader.decoder.DecodeResult('STRUCTURAL_OBSERVATION_READY','ARCHIVE_RECHECK',
            Observation(row['public_id'], stamp, row['price'], row['image_url'],
                        stamp, stamp, stamp, 'VALID'), row['price_is_lower_bound']))
    receipt, canonical = handoff.build(source_bytes, sha256(source_bytes).hexdigest(),
        expected_database_sha256, tuple(decoded), batch_index=batch_index, evaluated_at=evaluated_at)
    if canonical is None or canonical != data:
        raise ValueError('PAYLOAD_REVALIDATION_FAILED')


def encode(evidence, source_bytes, *, expected_database_sha256, batch_index,
           authentication_key, evaluated_at):
    """Bytes only. Requires a currently owned capture, never arbitrary JSON."""
    if type(authentication_key) is not bytes or len(authentication_key) < 32:
        raise ValueError('AUTHENTICATION_KEY_REQUIRED')
    if type(evidence) is not Capture or _OWNED.get(id(evidence)) is not evidence or evidence.api_calls != 5:
        raise ValueError('OWNED_CAPTURE_REQUIRED')
    _validate(evidence._data, source_bytes, expected_database_sha256, batch_index, evaluated_at)
    payload = dict(version=VERSION, handoff=json.loads(evidence._data))
    signature = hmac.new(authentication_key, DOMAIN + _json(payload), 'sha256').hexdigest()
    return _json(dict(payload=payload, authentication=signature))


def verify(data, source_bytes, *, expected_database_sha256, batch_index,
           authentication_key, evaluated_at):
    """Validate a signed format; returns aggregate result, no owned capability.

    No load/save, DPAPI or arbitrary archive-to-owned-capture conversion.
    """
    try:
        if (type(authentication_key) is not bytes or len(authentication_key) < 32
                or type(data) is not bytes or len(data) > MAX_BYTES):
            raise ValueError
        envelope = json.loads(data, object_pairs_hook=_unique)
        if type(envelope) is not dict or set(envelope) != {'payload','authentication'}:
            raise ValueError
        payload = envelope['payload']
        if (type(payload) is not dict or set(payload) != {'version','handoff'}
                or payload['version'] != VERSION or type(envelope['authentication']) is not str):
            raise ValueError
        expected = hmac.new(authentication_key, DOMAIN + _json(payload), 'sha256').hexdigest()
        if not hmac.compare_digest(expected, envelope['authentication']):
            raise ValueError
        _validate(_json(payload['handoff']), source_bytes, expected_database_sha256, batch_index, evaluated_at)
        return dict(status='AUTHENTICATED_FORMAT_VERIFIED', record_count=5,
                    publication_allowed=False, database_write_performed=False,
                    output_written=False, owned_capture_issued=False)
    except Exception:
        return dict(status='BLOCKED', reason_code='ARCHIVE_VERIFICATION_FAILED',
                    publication_allowed=False, database_write_performed=False,
                    output_written=False, owned_capture_issued=False)
