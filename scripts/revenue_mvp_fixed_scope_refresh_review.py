"""Pure structural review of fixed-scope refresh inputs; never authorization.

No API, database, filesystem, scheduler, rendering, or publication operations.
Caller-supplied observations and hashes do not establish trusted provenance.
A later integration must independently validate official evidence and approval.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from html.parser import HTMLParser
import re
from urllib.parse import urlsplit

ID = re.compile(r"itm_[0-9a-f]{24}\Z")
MAX_AGE = timedelta(hours=24)


@dataclass(frozen=True)
class Observation:
    public_id: str
    observed_at: datetime
    price: int | None
    image_url: str | None
    price_observed_at: datetime
    image_observed_at: datetime
    lifecycle_observed_at: datetime
    outcome: str


@dataclass(frozen=True)
class Receipt:
    status: str
    reason_code: str
    scope_count: int = 0
    observation_count: int = 0
    publication_allowed: bool = False
    api_request_performed: bool = False
    database_write_performed: bool = False
    production_write_performed: bool = False


class ScopeParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.cards = []
        self.card = None
        self.in_time = False

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "article" and "item" in values.get("class", "").split():
            if self.card is not None:
                raise ValueError
            self.card = {"ids": [], "times": []}
        if self.card is not None and tag == "a":
            href = values.get("href", "")
            if href.startswith("/go/"):
                self.card["ids"].append(href[4:])
        if self.card is not None and tag == "time":
            self.card["times"].append("")
            self.in_time = True

    def handle_data(self, data):
        if self.card is not None and self.in_time:
            self.card["times"][-1] += data

    def handle_endtag(self, tag):
        if tag == "time":
            self.in_time = False
        if tag == "article" and self.card is not None:
            self.cards.append(self.card)
            self.card = None


def utc(value):
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError
    return value.astimezone(timezone.utc)


def image_valid(value):
    if type(value) is not str or any(ord(c) <= 32 for c in value):
        return False
    try:
        parsed = urlsplit(value)
        return (parsed.scheme == "https" and parsed.netloc == "pics.dmm.co.jp"
                and parsed.username is None and parsed.password is None
                and parsed.port is None and bool(parsed.path.strip("/"))
                and not parsed.query and not parsed.fragment)
    except ValueError:
        return False


def review(source: bytes, expected_sha256: str, observations: tuple[Observation, ...],
           *, evaluated_at: datetime) -> Receipt:
    def blocked(reason, count=0):
        return Receipt("BLOCKED", reason, count)
    try:
        now = utc(evaluated_at)
        if (type(source) is not bytes or type(expected_sha256) is not str
                or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256)
                or sha256(source).hexdigest() != expected_sha256):
            return blocked("SOURCE_BINDING_INVALID")
        parser = ScopeParser()
        parser.feed(source.decode("utf-8"))
        parser.close()
        if parser.card is not None or len(parser.cards) != 100:
            return blocked("FIXED_SCOPE_INVALID")
        scope = {}
        for card in parser.cards:
            if len(card["ids"]) != 1 or len(card["times"]) != 1:
                return blocked("FIXED_SCOPE_INVALID")
            identity = card["ids"][0]
            if not ID.fullmatch(identity) or identity in scope:
                return blocked("FIXED_SCOPE_INVALID")
            stamp = datetime.fromisoformat(card["times"][0].strip().replace("Z", "+00:00"))
            scope[identity] = utc(stamp)
        if type(observations) is not tuple or len(observations) != 100:
            return blocked("OBSERVATION_COVERAGE_INVALID", 100)
        seen = set()
        for row in observations:
            if type(row) is not Observation or type(row.public_id) is not str:
                return blocked("OBSERVATION_INVALID", 100)
            if row.public_id not in scope or row.public_id in seen:
                return blocked("SCOPE_CHANGED_OR_DUPLICATED", 100)
            seen.add(row.public_id)
            if row.outcome == "NOT_AVAILABLE":
                return blocked("SEPARATE_TAKEDOWN_REVIEW_REQUIRED", 100)
            if row.outcome != "VALID":
                return blocked("OBSERVATION_UNCONFIRMED", 100)
            stamp = utc(row.observed_at)
            if (not timedelta(0) <= now - stamp <= MAX_AGE
                    or stamp <= scope[row.public_id]):
                return blocked("OBSERVATION_STALE_OR_NOT_NEW", 100)
            if any(utc(t) != stamp for t in (
                    row.price_observed_at, row.image_observed_at,
                    row.lifecycle_observed_at)):
                return blocked("FIELD_PROVENANCE_MISMATCH", 100)
            if type(row.price) is not int or row.price < 0 or not image_valid(row.image_url):
                return blocked("FIELD_INVALID", 100)
        return Receipt("STRUCTURAL_REVIEW_READY", "TRUSTED_EVIDENCE_AND_APPROVAL_REQUIRED",
                       100, 100)
    except (ValueError, TypeError, UnicodeError, AttributeError, OverflowError):
        return blocked("INPUT_INVALID")
