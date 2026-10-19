"""Offline-only exact-100 refresh registration preparation; never execution.

Returns private SQL bytes, never writes them. Caller-supplied snapshot timestamps
and hashes do not prove remote provenance or authorize a D1 operation.
"""
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import re
import sqlite3

from revenue_mvp_lifecycle_receipt import public_item_id
import revenue_mvp_product_refresh_preapproval as preapproval

READY = "OFFLINE_REGISTRATION_BATCH_PREPARED"
BLOCKED = "BLOCKED"
BATCH_SIZE = 5
MAX_SNAPSHOT_AGE = timedelta(minutes=15)
ID = re.compile(r"itm_[0-9a-f]{24}\Z")
CONTENT = re.compile(r"[A-Za-z0-9._-]{1,128}\Z")
HASH = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class Receipt:
    status: str
    reason_code: str
    missing_count: int = 0
    selected_count: int = 0
    batch_index: int = 0
    batch_count: int = 0
    sql_sha256: str | None = None
    database_unchanged: bool = False
    output_written: bool = False
    publication_allowed: bool = False
    api_request_performed: bool = False
    d1_write_performed: bool = False
    explicit_live_approval_required: bool = True
    authoritative_snapshot_provenance_verified: bool = False
    source_sha256: str | None = None
    candidate_sha256: str | None = None
    database_sha256: str | None = None
    snapshot_sha256: str | None = None

    def to_dict(self):
        return asdict(self)


def _digest(value):
    return hashlib.sha256(value).hexdigest()


def _ids(html):
    if type(html) is not bytes or len(html) > 2 * 1024 * 1024:
        raise ValueError("HTML_BOUNDARY_INVALID")
    matches = re.findall(rb'href="/go/([^"\s]*)"', html)
    values = [value.decode("ascii") for value in matches]
    if len(values) != 100 or len(set(values)) != 100 or any(not ID.fullmatch(v) for v in values):
        raise ValueError("EXACT_100_SURFACE_REQUIRED")
    return set(values)


def prepare(source: bytes, candidate: bytes, database: Path, snapshot: bytes, *,
            expected_source_sha256: str, expected_candidate_sha256: str,
            expected_database_sha256: str, expected_snapshot_sha256: str,
            snapshot_observed_at: datetime, evaluated_at: datetime,
            expected_missing_count: int, batch_index: int) -> tuple[Receipt, bytes | None]:
    """Pure local preparation apart from query-only DB reads and in-memory SQL.

    Exactly 99 introduced routes are required. The missing set is rederived from
    a supplied mapping snapshot, not from aggregate counts. SQL is INSERT-only;
    a later executor must independently recheck provenance, freshness and state.
    """
    local = remote = None
    try:
        hashes = (expected_source_sha256, expected_candidate_sha256,
                  expected_database_sha256, expected_snapshot_sha256)
        if any(type(value) is not str or not HASH.fullmatch(value) for value in hashes):
            raise ValueError("EXPECTED_HASH_INVALID")
        if (type(snapshot) is not bytes or len(snapshot) > 16 * 1024 * 1024
                or _digest(source) != expected_source_sha256
                or _digest(candidate) != expected_candidate_sha256
                or _digest(snapshot) != expected_snapshot_sha256):
            raise ValueError("INPUT_IDENTITY_MISMATCH")
        if (type(batch_index) is not int or batch_index < 0
                or type(expected_missing_count) is not int or not 1 <= expected_missing_count <= 99):
            raise ValueError("BATCH_BOUNDARY_INVALID")
        if (not isinstance(evaluated_at, datetime) or evaluated_at.tzinfo is None
                or not isinstance(snapshot_observed_at, datetime) or snapshot_observed_at.tzinfo is None):
            raise ValueError("TIMESTAMP_INVALID")
        age = evaluated_at.astimezone(timezone.utc) - snapshot_observed_at.astimezone(timezone.utc)
        if not timedelta(0) <= age <= MAX_SNAPSHOT_AGE:
            raise ValueError("SNAPSHOT_STALE_OR_FUTURE")
        source_ids, candidate_ids = _ids(source), _ids(candidate)
        added = candidate_ids - source_ids
        if len(added) != 99 or len(source_ids - candidate_ids) != 99:
            raise ValueError("EXACT_99_DELTA_REQUIRED")
        if (not isinstance(database, Path) or not database.is_file()
                or any(path.is_symlink() for path in (database, *database.parents))
                or any(Path(str(database) + suffix).exists() for suffix in ("-wal", "-shm", "-journal"))):
            raise ValueError("DATABASE_BOUNDARY_INVALID")
        if _digest(database.read_bytes()) != expected_database_sha256:
            raise ValueError("DATABASE_IDENTITY_MISMATCH")
        local = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
        local.execute("PRAGMA query_only=ON")
        mappings = {}
        for site, service, floor, content in local.execute("SELECT site,service,floor,content_id FROM items"):
            if (site, service, floor) != ("FANZA", "digital", "videoa"):
                continue
            if type(content) is not str or not CONTENT.fullmatch(content):
                raise ValueError("LOCAL_MAPPING_INVALID")
            public = public_item_id(site, service, floor, content)
            if public in candidate_ids:
                if public in mappings:
                    raise ValueError("LOCAL_MAPPING_DUPLICATE")
                mappings[public] = content
        if set(mappings) != candidate_ids:
            raise ValueError("LOCAL_MAPPING_COVERAGE_INVALID")
        remote = sqlite3.connect(":memory:")
        remote.executescript(preapproval.SCHEMA.read_text(encoding="utf-8"))
        preapproval._load_private_d1_export(remote, snapshot)
        before = remote.execute("SELECT * FROM affiliate_item_lookup ORDER BY public_id").fetchall()
        by_public = {row[0]: row[1] for row in before}
        by_content = {row[1]: row[0] for row in before}
        for public, content in mappings.items():
            if ((public in by_public and by_public[public] != content)
                    or (content in by_content and by_content[content] != public)):
                raise ValueError("D1_MAPPING_CONFLICT")
        missing = sorted(candidate_ids - set(by_public))
        if len(missing) != expected_missing_count or not set(missing) <= added:
            raise ValueError("MISSING_SCOPE_MISMATCH")
        batches = (len(missing) + BATCH_SIZE - 1) // BATCH_SIZE
        if batch_index >= batches:
            raise ValueError("BATCH_INDEX_OUT_OF_RANGE")
        selected = missing[batch_index * BATCH_SIZE:(batch_index + 1) * BATCH_SIZE]
        sql = ("INSERT INTO affiliate_item_lookup "
               "(public_id,content_id,rights_status,lifecycle_status,verification_status,affiliate_enabled,updated_at) VALUES "
               + ",".join(f"('{public}','{mappings[public]}','PENDING_SEPARATE_POLICY',"
                          "'PENDING_OFFICIAL_CONFIRMATION','PENDING',0,'1970-01-01T00:00:00Z')"
                          for public in selected) + ";")
        untouched_tables = ("affiliate_redirect_target", "affiliate_lifecycle_revalidation_event")
        untouched = [remote.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall() for table in untouched_tables]
        eligible_before = remote.execute("SELECT count(*) FROM affiliate_runtime_eligible_lookup").fetchone()[0]
        remote.execute(sql)
        after = remote.execute("SELECT * FROM affiliate_item_lookup ORDER BY public_id").fetchall()
        new_rows = [row for row in after if row[0] not in by_public]
        if ([row for row in after if row[0] in by_public] != before
                or len(new_rows) != len(selected)
                or any(row[2:] != ('PENDING_SEPARATE_POLICY', 'PENDING_OFFICIAL_CONFIRMATION',
                                  'PENDING', 0, '1970-01-01T00:00:00Z') for row in new_rows)
                or remote.execute("SELECT count(*) FROM affiliate_runtime_eligible_lookup").fetchone()[0] != eligible_before
                or untouched != [remote.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall() for table in untouched_tables]):
            raise ValueError("ISOLATED_POSTCONDITION_FAILED")
        if (_digest(database.read_bytes()) != expected_database_sha256
                or any(Path(str(database) + suffix).exists() for suffix in ("-wal", "-shm", "-journal"))):
            raise ValueError("DATABASE_CHANGED_DURING_PREPARATION")
        payload = sql.encode("ascii")
        return Receipt(READY, "OFFLINE_DISABLED_INSERT_ONLY", len(missing), len(selected),
                       batch_index, batches, _digest(payload), True,
                       source_sha256=expected_source_sha256,
                       candidate_sha256=expected_candidate_sha256,
                       database_sha256=expected_database_sha256,
                       snapshot_sha256=expected_snapshot_sha256), payload
    except ValueError as error:
        # Only fixed local reason codes may be exposed; never SQL/DB exception text.
        reason = str(error)
        if re.fullmatch(r"[A-Z][A-Z0-9_]{1,80}", reason) is None:
            reason = "PREPARATION_INPUT_INVALID"
        return Receipt(BLOCKED, reason), None
    except (OSError, sqlite3.Error, TypeError, UnicodeError, KeyError):
        return Receipt(BLOCKED, "PREPARATION_FAILED_SAFE"), None
    finally:
        if local is not None:
            local.close()
        if remote is not None:
            remote.close()
