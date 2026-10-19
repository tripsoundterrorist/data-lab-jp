"""Secret-safe, opt-in D1 query transport for bounded initial revalidation.

Specification: https://developers.cloudflare.com/api/resources/d1/subresources/database/methods/query/
Credentials are explicitly injected; no environment/cache reads, subprocesses,
temporary SQL, logging, redirects or automatic retries. A response is not a
substitute for independent post-write verification.
"""
from dataclasses import dataclass, field
from datetime import datetime
import json
import re
import urllib.request

import affiliate_local_lifecycle_revalidation as shared

PENDING = ("rights_status='PENDING_SEPARATE_POLICY' AND "
           "lifecycle_status='PENDING_OFFICIAL_CONFIRMATION' AND "
           "verification_status='PENDING' AND affiliate_enabled=0")
TARGET = ("INSERT INTO affiliate_redirect_target (public_id,content_id,affiliate_url,verified_at) "
          "SELECT public_id,content_id,?,? FROM affiliate_item_lookup "
          "WHERE public_id=? AND content_id=? AND " + PENDING)
EVENT = ("INSERT INTO affiliate_lifecycle_revalidation_event "
         "(public_id,checked_at,outcome,affiliate_enabled_after,reason_code) "
         "SELECT public_id,?,?,?,? FROM affiliate_item_lookup "
         "WHERE public_id=? AND content_id=? AND " + PENDING)
ENABLE = ("UPDATE affiliate_item_lookup SET rights_status='CONDITIONALLY_APPROVED',"
          "lifecycle_status='RESOLVED',verification_status='PASS',affiliate_enabled=1,updated_at=? "
          "WHERE public_id=? AND content_id=? AND " + PENDING)
FAIL = ("UPDATE affiliate_item_lookup SET verification_status='FAILED',affiliate_enabled=0,updated_at=? "
        "WHERE public_id=? AND content_id=? AND " + PENDING)
KEEP_PENDING = ("UPDATE affiliate_item_lookup SET verification_status='PENDING',affiliate_enabled=0,updated_at=? "
                "WHERE public_id=? AND content_id=? AND " + PENDING)
SAFE_SQL = frozenset((TARGET, EVENT, ENABLE, FAIL, KEEP_PENDING))


@dataclass(frozen=True)
class Query:
    sql: str = field(repr=False)
    params: tuple[str, ...] = field(repr=False)


@dataclass(frozen=True)
class Outcome:
    state: str
    statement_count: int = 0
    reason_code: str = ""


def build_queries(rows, outcomes, checked):
    if not 1 <= len(rows) <= 5 or len(rows) != len(outcomes):
        raise ValueError("QUERY_SCOPE_INVALID")
    if type(checked) is not str or len(checked) > 64:
        raise ValueError("QUERY_TIMESTAMP_INVALID")
    try:
        stamp = datetime.fromisoformat(checked.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("QUERY_TIMESTAMP_INVALID") from None
    if stamp.tzinfo is None or not checked.endswith("Z"):
        raise ValueError("QUERY_TIMESTAMP_INVALID")
    seen_public, seen_content, queries = set(), set(), []
    for row, (outcome, url) in zip(rows, outcomes, strict=True):
        public, content = row["public_id"], row["content_id"]
        if (type(public) is not str or not shared.PUBLIC_ID.fullmatch(public)
                or type(content) is not str or not shared.CONTENT_ID.fullmatch(content)
                or public in seen_public or content in seen_content):
            raise ValueError("QUERY_IDENTITY_INVALID")
        seen_public.add(public)
        seen_content.add(content)
        if outcome == "VALID":
            if not shared._safe_url(url):
                raise ValueError("QUERY_URL_INVALID")
            queries.append(Query(TARGET, (url, checked, public, content)))
            enabled, reason, update = "1", "OFFICIAL_API_EXACT_MATCH", ENABLE
        elif outcome in ("NOT_AVAILABLE", "UNCONFIRMED") and url is None:
            enabled = "0"
            reason = "OFFICIAL_API_ITEM_UNAVAILABLE" if outcome == "NOT_AVAILABLE" else "LOCAL_UPSTREAM_UNCONFIRMED"
            update = FAIL if outcome == "NOT_AVAILABLE" else KEEP_PENDING
        else:
            raise ValueError("QUERY_OUTCOME_INVALID")
        queries.append(Query(EVENT, (checked, outcome, enabled, reason, public, content)))
        queries.append(Query(update, (checked, public, content)))
    return tuple(queries)


def _canonical_batch(queries):
    rows, outcomes, checked = [], [], None
    index = 0
    while index < len(queries):
        target = queries[index] if queries[index].sql == TARGET else None
        event = queries[index + 1] if target is not None else queries[index]
        if event.sql != EVENT:
            return False
        stamp, outcome, _, _, public, content = event.params
        if checked is not None and checked != stamp:
            return False
        checked = stamp
        rows.append({"public_id": public, "content_id": content})
        outcomes.append((outcome, target.params[0] if target is not None else None))
        index += 3 if target is not None else 2
    return build_queries(rows, outcomes, checked) == queries


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _open(request, *, timeout):
    return urllib.request.build_opener(_NoRedirect()).open(request, timeout=timeout)


class D1QueryClient:
    """One explicit in-memory query POST; transport exceptions are never exposed."""
    def __init__(self, account_id, database_id, credential_provider, *, opener=_open):
        if (type(account_id) is not str or re.fullmatch(r"[0-9a-f]{32}", account_id) is None
                or type(database_id) is not str
                or re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", database_id) is None
                or not callable(credential_provider) or not callable(opener)):
            raise ValueError("D1_QUERY_CONFIG_INVALID")
        self._endpoint = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/d1/database/{database_id}/query"
        self._credential_provider = credential_provider
        self._opener = opener
        self._token = None
        self._used = False

    def __repr__(self):
        return "D1QueryClient([REDACTED])"

    def ready(self):
        self._token = None
        if self._used:
            return False
        try:
            token = self._credential_provider()
            if type(token) is not str or not 1 <= len(token) <= 4096 or any(not 33 <= ord(c) <= 126 for c in token):
                return False
            self._token = token
            return True
        except Exception:
            return False

    def clear(self):
        self._token = None

    def write(self, queries, *, confirmed=False):
        if confirmed is not True or self._used or self._token is None:
            return Outcome("NOT_ATTEMPTED", reason_code="D1_QUERY_NOT_AUTHORIZED_OR_READY")
        try:
            if (type(queries) is not tuple or not 2 <= len(queries) <= 15
                    or any(type(q) is not Query or q.sql not in SAFE_SQL
                           or type(q.params) is not tuple or len(q.params) != q.sql.count("?")
                           or any(type(v) is not str or len(v) > 4096 for v in q.params) for q in queries)
                    or not _canonical_batch(queries)):
                return Outcome("NOT_ATTEMPTED", reason_code="D1_QUERY_BATCH_INVALID")
            body = json.dumps({"batch": [{"sql": q.sql, "params": list(q.params)} for q in queries]}).encode("utf-8")
            request = urllib.request.Request(self._endpoint, data=body, method="POST",
                headers={"Authorization": "Bearer " + self._token, "Content-Type": "application/json", "Accept": "application/json"})
        except Exception:
            return Outcome("NOT_ATTEMPTED", reason_code="D1_QUERY_REQUEST_INVALID")
        self._used = True
        try:
            with self._opener(request, timeout=30) as response:
                if response.status != 200:
                    return Outcome("UNKNOWN", len(queries), "D1_QUERY_HTTP_UNCONFIRMED")
                raw = response.read(262145)
            if len(raw) > 262144:
                return Outcome("UNKNOWN", len(queries), "D1_QUERY_RESPONSE_TOO_LARGE")
            payload = json.loads(raw)
            results = payload.get("result") if isinstance(payload, dict) else None
            if (not isinstance(payload, dict) or payload.get("success") is not True
                    or payload.get("errors") != [] or type(results) is not list or len(results) != len(queries)
                    or any(type(row) is not dict or row.get("success") is not True
                           or type(row.get("meta")) is not dict
                           or type(row["meta"].get("changes")) is not int or row["meta"]["changes"] != 1
                           or row.get("results", []) != [] for row in results)):
                return Outcome("UNKNOWN", len(queries), "D1_QUERY_RESULT_UNCONFIRMED")
            return Outcome("APPLIED", len(queries), "D1_QUERY_ACKNOWLEDGED_POSTCHECK_REQUIRED")
        except Exception:
            return Outcome("UNKNOWN", len(queries), "D1_QUERY_WRITE_UNCONFIRMED")
        finally:
            self._token = None
