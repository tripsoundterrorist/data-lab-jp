"""Build and preflight a scoped, insert-only disabled expansion delta."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from typing import Any

import affiliate_d1_incremental_reconciliation as reconciliation
from validate_affiliate_item_lookup_candidate import _snapshot_regular_file


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "runtime-candidates" / "affiliate-item-lookup-schema.sql"
VERSION = "0.1"
READY = "SCOPED_DISABLED_DELTA_READY"
BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class DeltaReceipt:
    version: str
    status: str
    remote_row_count: int
    candidate_row_count: int
    exact_match_count: int
    delta_row_count: int
    final_row_count: int
    mapping_conflict_count: int
    existing_rows_unchanged: bool
    new_rows_disabled_and_pending: bool
    runtime_eligibility_unchanged: bool
    delta_written: bool
    delta_sha256: str | None
    production_write_performed: bool
    publication_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _blocked(reason: str) -> DeltaReceipt:
    return DeltaReceipt(
        VERSION, BLOCKED, 0, 0, 0, 0, 0, 0, False, False, False,
        False, None, False, False, (reason,),
    )


def build(
    remote_bytes: bytes,
    candidate_bytes: bytes,
    schema_bytes: bytes,
    *,
    expected_remote_sha256: Any,
    expected_candidate_sha256: Any,
) -> tuple[DeltaReceipt, bytes | None]:
    connection: sqlite3.Connection | None = None
    try:
        if (
            type(expected_remote_sha256) is not str
            or type(expected_candidate_sha256) is not str
            or hashlib.sha256(remote_bytes).hexdigest() != expected_remote_sha256
            or hashlib.sha256(candidate_bytes).hexdigest() != expected_candidate_sha256
        ):
            return _blocked("IDENTITY_MISMATCH"), None
        candidate_rows = reconciliation._parse_candidate(candidate_bytes)
        connection = sqlite3.connect(":memory:")
        connection.executescript(schema_bytes.decode("utf-8"))
        connection.executescript(remote_bytes.decode("utf-8"))
        remote_rows = connection.execute(
            "SELECT public_id,content_id FROM affiliate_item_lookup ORDER BY public_id"
        ).fetchall()
        if len(candidate_rows) != 300 or not reconciliation._unique_mapping(remote_rows):
            return _blocked("INPUT_MAPPING_INVALID"), None
        if not reconciliation._unique_mapping(candidate_rows):
            return _blocked("CANDIDATE_MAPPING_INVALID"), None

        remote_set = set(remote_rows)
        remote_by_public = dict(remote_rows)
        remote_by_content = {content_id: public_id for public_id, content_id in remote_rows}
        matches = 0
        conflicts = 0
        missing: list[tuple[str, str]] = []
        for public_id, content_id in candidate_rows:
            if (public_id, content_id) in remote_set:
                matches += 1
            elif public_id in remote_by_public or content_id in remote_by_content:
                conflicts += 1
            else:
                missing.append((public_id, content_id))
        if conflicts:
            return _blocked("MAPPING_CONFLICT_DETECTED"), None

        lines = ["INSERT INTO affiliate_item_lookup (public_id, content_id, updated_at) VALUES"]
        lines.extend(
            f"('{public_id}', '{content_id}', '1970-01-01T00:00:00Z')"
            + ("," if index < len(missing) - 1 else ";")
            for index, (public_id, content_id) in enumerate(missing)
        )
        if not missing:
            return _blocked("NO_MISSING_ROWS"), None
        delta = ("\n".join(lines) + "\n").encode("utf-8")

        before = connection.execute(
            "SELECT * FROM affiliate_item_lookup ORDER BY public_id"
        ).fetchall()
        eligible_before = connection.execute(
            "SELECT count(*) FROM affiliate_runtime_eligible_lookup"
        ).fetchone()[0]
        connection.executescript(delta.decode("utf-8"))
        existing_after = connection.execute(
            "SELECT * FROM affiliate_item_lookup WHERE public_id IN ({}) ORDER BY public_id".format(
                ",".join("?" for _ in before)
            ), tuple(row[0] for row in before),
        ).fetchall()
        final_count = connection.execute(
            "SELECT count(*) FROM affiliate_item_lookup"
        ).fetchone()[0]
        eligible_after = connection.execute(
            "SELECT count(*) FROM affiliate_runtime_eligible_lookup"
        ).fetchone()[0]
        new_invalid = connection.execute(
            """SELECT count(*) FROM affiliate_item_lookup
               WHERE public_id NOT IN ({}) AND (
                 rights_status!='PENDING_SEPARATE_POLICY'
                 OR lifecycle_status!='PENDING_OFFICIAL_CONFIRMATION'
                 OR verification_status!='PENDING' OR affiliate_enabled!=0
                 OR updated_at!='1970-01-01T00:00:00Z')""".format(
                ",".join("?" for _ in before)
            ), tuple(row[0] for row in before),
        ).fetchone()[0]
        if not (
            existing_after == before
            and final_count == len(remote_rows) + len(missing)
            and eligible_after == eligible_before
            and new_invalid == 0
        ):
            return _blocked("ISOLATED_POSTCONDITION_FAILED"), None
        receipt = DeltaReceipt(
            VERSION, READY, len(remote_rows), len(candidate_rows), matches,
            len(missing), final_count, 0, True, True, True, False,
            hashlib.sha256(delta).hexdigest(), False, False,
            (
                "EXISTING_ROWS_PRESERVED", "NEW_ROWS_DISABLED_AND_PENDING",
                "RUNTIME_ELIGIBILITY_UNCHANGED", "D1_WRITE_NOT_AUTHORIZED",
            ),
        )
        return receipt, delta
    except (UnicodeError, ValueError, sqlite3.Error, TypeError):
        return _blocked("INPUT_OR_PREFLIGHT_INVALID"), None
    except Exception:
        return _blocked("DELTA_BUILD_FAILED"), None
    finally:
        if connection is not None:
            connection.close()


def build_files(remote: Path, candidate: Path, output: Path, *, private_root: Path, **kwargs: Any) -> DeltaReceipt:
    temporary: Path | None = None
    try:
        if (
            any(path.is_symlink() for path in (remote, candidate, output, private_root, SCHEMA))
            or not private_root.is_dir() or output.parent.resolve() != private_root.resolve()
            or output.suffix.lower() != ".sql" or output.exists()
        ):
            return _blocked("OUTPUT_BOUNDARY_INVALID")
        receipt, delta = build(
            _snapshot_regular_file(remote), _snapshot_regular_file(candidate),
            _snapshot_regular_file(SCHEMA), **kwargs,
        )
        if receipt.status != READY or delta is None:
            return receipt
        handle = tempfile.NamedTemporaryFile(
            mode="wb", dir=private_root, prefix=".expansion-delta-", suffix=".tmp", delete=False
        )
        temporary = Path(handle.name)
        with handle:
            handle.write(delta)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o600)
        os.replace(temporary, output)
        temporary = None
        return DeltaReceipt(**{**asdict(receipt), "delta_written": True})
    except (OSError, RuntimeError):
        return _blocked("FILESYSTEM_OPERATION_FAILED")
    finally:
        if temporary is not None and temporary.exists():
            try:
                temporary.unlink()
            except OSError:
                pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a private scoped disabled D1 delta.")
    parser.add_argument("--remote", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--expected-remote-sha256", required=True)
    parser.add_argument("--expected-candidate-sha256", required=True)
    args = parser.parse_args(argv)
    receipt = build_files(
        args.remote, args.candidate, args.output, private_root=args.private_root,
        expected_remote_sha256=args.expected_remote_sha256,
        expected_candidate_sha256=args.expected_candidate_sha256,
    )
    print(json.dumps(receipt.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if receipt.status == READY and receipt.delta_written else 2


if __name__ == "__main__":
    raise SystemExit(main())
