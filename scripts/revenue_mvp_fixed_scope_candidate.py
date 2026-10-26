"""Pure signed-batch aggregation and fixed-100 price/image review candidate.

No file reads/writes, DPAPI, API requests, DB access or publication. Keys must
be supplied from a separately approved trusted source. Caller-created sets are
not accepted by the renderer. HMAC proves integrity, not current availability.
Visible historical dates and titles stay unchanged; field dates are returned
separately, and date-display review is required before any public adoption.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from html import escape
import json
import re
from weakref import WeakValueDictionary

import revenue_mvp_fixed_scope_capture as archive
from revenue_mvp_fixed_scope_acquisition_plan import build as plan_scope

_SETS = WeakValueDictionary()
MAX_SOURCE_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class _Record:
    public_id: str
    price: int
    lower_bound: bool
    image_url: str = field(repr=False)
    observed_at: datetime


@dataclass(frozen=True, eq=False)
class ArchiveSet:
    source_sha256: str
    database_sha256: str
    _records: tuple = field(repr=False)


def _receipt(status='BLOCKED', reason='INPUT_INVALID', count=0):
    return dict(status=status, reason_code=reason, record_count=count,
                api_calls=0, key_read_performed=False, output_written=False,
                database_write_performed=False, publication_allowed=False)


def _utc(value):
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('UTC_TIME_REQUIRED')
    return value.astimezone(timezone.utc)


def aggregate(archives, source, *, expected_source_sha256, expected_database_sha256,
              authentication_key, evaluated_at):
    """Exactly 20 authenticated batches; no arbitrary field merging or IO."""
    def stop(reason):
        return _receipt(reason=reason), None
    try:
        now = _utc(evaluated_at)
        if type(source) is not bytes or len(source) > MAX_SOURCE_BYTES:
            return stop('SOURCE_INVALID')
        plan = plan_scope(source, expected_source_sha256)
        if plan.status != 'OFFLINE_PLAN_READY':
            return stop('SOURCE_BINDING_OR_SCOPE_INVALID')
        if type(archives) is not tuple or len(archives) != 20:
            return stop('EXACT_TWENTY_BATCHES_REQUIRED')
        batches = set()
        records = []
        for data in archives:
            if type(data) is not bytes or len(data) > archive.MAX_BYTES:
                return stop('ARCHIVE_INVALID')
            # Index is used only to select verification scope; never trusted yet.
            envelope = json.loads(data, object_pairs_hook=archive._unique)
            index = envelope['payload']['handoff']['batch_index']
            if type(index) is not int or not 0 <= index < 20 or index in batches:
                return stop('BATCH_CHANGED_OR_DUPLICATED')
            verified = archive.verify(data, source, expected_database_sha256=expected_database_sha256,
                batch_index=index, authentication_key=authentication_key, evaluated_at=now)
            if verified['status'] != 'AUTHENTICATED_FORMAT_VERIFIED':
                return stop('ARCHIVE_UNCONFIRMED')
            batches.add(index)
            for row in envelope['payload']['handoff']['records']:
                records.append(_Record(row['public_id'], row['price'], row['price_is_lower_bound'],
                                       row['image_url'], _utc(datetime.fromisoformat(row['observed_at']))))
        expected = {pid for batch in plan.batches for pid in batch}
        if (batches != set(range(20)) or len(records) != 100
                or len({row.public_id for row in records}) != 100
                or {row.public_id for row in records} != expected):
            return stop('FIXED_HUNDRED_COVERAGE_INVALID')
        result = ArchiveSet(expected_source_sha256, expected_database_sha256,
                            tuple(sorted(records, key=lambda row: row.public_id)))
        _SETS[id(result)] = result
        return _receipt('AUTHENTICATED_FIXED_HUNDRED_REVIEW_READY',
                        'NO_DATABASE_OR_PUBLICATION_AUTHORITY',100), result
    except (TypeError,ValueError,KeyError,AttributeError,OverflowError,UnicodeError):
        return stop('INPUT_INVALID')


def build_candidate(verified_set, source, *, evaluated_at):
    """Return bytes and field-date sidecar only; preserve visible source dates.

    The restrictive HTML shape deliberately fails on layout changes. It is not
    a generic sanitizer and does not certify unchanged historical HTML safety.
    """
    def stop(reason):
        return _receipt(reason=reason), None, None
    try:
        now = _utc(evaluated_at)
        if (type(verified_set) is not ArchiveSet or _SETS.get(id(verified_set)) is not verified_set):
            return stop('OWNED_VERIFIED_ARCHIVE_SET_REQUIRED')
        if (type(source) is not bytes or len(source)>MAX_SOURCE_BYTES
                or sha256(source).hexdigest()!=verified_set.source_sha256):
            return stop('SOURCE_CHANGED')
        if any(not timedelta(0)<=now-row.observed_at<=timedelta(hours=24) for row in verified_set._records):
            return stop('ARCHIVE_SET_STALE_OR_FUTURE')
        records={row.public_id:row for row in verified_set._records}
        text=source.decode('utf-8')
        card_pattern=re.compile(r'<article class="item">.*?</article>',re.DOTALL)
        cards=list(card_pattern.finditer(text))
        if len(cards)!=100:
            return stop('CARD_SHAPE_INVALID')
        seen=set()
        def update(match):
            card=match.group(0)
            identities=re.findall(r'href="/go/(itm_[0-9a-f]{24})"',card)
            if len(identities)!=1 or identities[0] in seen or identities[0] not in records:
                raise ValueError('CARD_IDENTITY_INVALID')
            identity=identities[0]; seen.add(identity)
            row=records[identity]
            price=f'{row.price:,}円'+('〜' if row.lower_bound else '')
            card,price_count=re.subn(r'(<p class="price">)[0-9,]+円(?:〜)?(</p>)',
                                    lambda m:m[1]+price+m[2],card)
            card,image_count=re.subn(r'(<img class="card-image" src=")[^"]*(")',
                                    lambda m:m[1]+escape(row.image_url,quote=True)+m[2],card)
            if price_count!=1 or image_count!=1:
                raise ValueError('PRICE_IMAGE_SHAPE_INVALID')
            return card
        candidate=card_pattern.sub(update,text).encode('utf-8')
        if seen!=set(records):
            return stop('FIXED_HUNDRED_COVERAGE_INVALID')
        metadata=dict(version='FIXED_HUNDRED_FIELD_DATES_1',
            source_sha256=verified_set.source_sha256,
            candidate_sha256=sha256(candidate).hexdigest(),
            database_sha256=verified_set.database_sha256,
            visible_historical_dates_preserved=True, title_freshness_renewed=False,
            publication_allowed=False,
            records=[dict(public_id=row.public_id,price_observed_at=row.observed_at.isoformat(),
                          image_observed_at=row.observed_at.isoformat()) for row in verified_set._records])
        receipt=_receipt('OFFLINE_FIXED_HUNDRED_CANDIDATE_READY',
                         'FIELD_DATE_DISPLAY_REVIEW_AND_PUBLICATION_APPROVAL_REQUIRED',100)
        receipt.update(candidate_sha256=metadata['candidate_sha256'],
                       retained_count=100,added_count=0,removed_count=0,
                       visible_historical_dates_preserved=True,title_freshness_renewed=False)
        return receipt,candidate,json.dumps(metadata,sort_keys=True,separators=(',',':')).encode()
    except (TypeError,ValueError,KeyError,AttributeError,OverflowError,UnicodeError):
        return stop('CANDIDATE_INPUT_OR_SHAPE_INVALID')
