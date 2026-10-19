"""Read-only snapshot-bound price-label correction; no network or writes."""
from hashlib import sha256
from html import escape
from pathlib import Path
import re
import sqlite3

from revenue_mvp_lifecycle_receipt import public_item_id
from revenue_mvp_product_card_reconciliation import reconcile, _utc_timestamp


def correct(source: bytes, database: Path, *, allow_missing_images: bool = False) -> bytes:
    if database.is_symlink() or any(Path(str(database)+s).exists() for s in ("-wal","-shm","-journal")):
        raise ValueError("PRICE_DATABASE_BOUNDARY_INVALID")
    before = sha256(database.read_bytes()).hexdigest()
    cards = reconcile(source, database, allow_missing_images=allow_missing_images)
    connection = sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA query_only=ON")
        rows = connection.execute(
            "SELECT i.site,i.service,i.floor,i.content_id,s.observed_at,s.price_raw,s.price_min "
            "FROM item_snapshots s JOIN items i ON i.id=s.item_id").fetchall()
    finally:
        connection.close()
    saved = {}
    for site, service, floor, cid, stamp, raw, price in rows:
        if not all(type(x) is str and x for x in (site,service,floor,cid)):
            continue
        key = (public_item_id(site,service,floor,cid), _utc_timestamp(stamp), price)
        saved.setdefault(key, []).append(raw)
    text = source.decode("utf-8")
    for card in cards:
        matches = saved.get((card.public_id,card.observed_at,card.price), [])
        if len(matches) != 1 or type(matches[0]) is not str:
            raise ValueError("PRICE_SNAPSHOT_BINDING_INVALID")
        match = re.fullmatch(r"([0-9]{1,12})(~?)", matches[0].strip())
        if match is None or int(match[1]) != card.price:
            raise ValueError("PRICE_RAW_INCONSISTENT")
        base = f'<h2>{escape(card.title)}</h2><p class="price">{card.price:,}円'
        tail = f'</p><time>{escape(card.observed_at)}</time>'
        exact, lower = base + tail, base + "〜" + tail
        if text.count(exact) + text.count(lower) != 1:
            raise ValueError("PRICE_HTML_BINDING_INVALID")
        current = lower if lower in text else exact
        replacement = lower if match[2] else exact
        text = text.replace(current, replacement, 1)
    if sha256(database.read_bytes()).hexdigest() != before:
        raise ValueError("PRICE_DATABASE_CHANGED")
    return text.encode("utf-8")


def stage_candidate(source: Path, database: Path, baseline: bytes, output: Path) -> dict:
    """Preserve the exact local correction privately; restore only our label delta.

    The baseline is not approval evidence. This performs no publication or Gate
    operation, and refuses overwrite, symlinks and unrelated local edits.
    """
    root = Path(__file__).resolve().parents[1]
    if source.is_symlink() or output.is_symlink() or output.exists():
        raise ValueError("STAGING_PATH_INVALID")
    try:
        output.resolve().relative_to(root.resolve())
    except ValueError:
        pass
    else:
        raise ValueError("CANDIDATE_MUST_BE_OUTSIDE_REPOSITORY")
    current = source.read_bytes()
    candidate = correct(baseline, database)
    if current != candidate or candidate.replace('円〜</p>'.encode(), '円</p>'.encode()) != baseline:
        raise ValueError("UNRELATED_LOCAL_CHANGES_PRESENT")
    if source.read_bytes() != current:
        raise ValueError("SOURCE_CHANGED")
    output.write_bytes(candidate)
    if sha256(output.read_bytes()).digest() != sha256(candidate).digest():
        raise ValueError("CANDIDATE_IDENTITY_INVALID")
    source.write_bytes(baseline)
    return {"status": "UNPUBLISHED_PRICE_CANDIDATE_STAGED",
            "baseline_sha256": sha256(baseline).hexdigest(),
            "candidate_sha256": sha256(candidate).hexdigest(),
            "lower_bound_labels": candidate.count('円〜</p>'.encode()),
            "publication_allowed": False, "database_write_performed": False}


def main():
    import argparse
    import json
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--db-sha256", required=True)
    parser.add_argument("--apply-local", action="store_true")
    args = parser.parse_args()
    try:
        if args.source.is_symlink() or args.db.is_symlink():
            raise ValueError("PATH_BOUNDARY_INVALID")
        original = args.source.read_bytes()
        if (sha256(original).hexdigest() != args.source_sha256
                or sha256(args.db.read_bytes()).hexdigest() != args.db_sha256):
            raise ValueError("INPUT_BINDING_INVALID")
        corrected = correct(original, args.db)
        if (args.source.read_bytes() != original
                or sha256(args.db.read_bytes()).hexdigest() != args.db_sha256):
            raise ValueError("INPUT_CHANGED")
        if args.apply_local:
            args.source.write_bytes(corrected)
        print(json.dumps({"status": "LOCAL_CORRECTION_APPLIED" if args.apply_local else "LOCAL_CORRECTION_READY",
                         "changed": corrected != original,
                         "lower_bound_labels": corrected.count('円〜</p>'.encode()),
                         "database_write_performed": False, "publication_allowed": False}))
        return 0
    except (ValueError, OSError, sqlite3.Error, UnicodeError):
        print(json.dumps({"status": "BLOCKED", "reason_code": "PRICE_LABEL_CORRECTION_FAILED"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
