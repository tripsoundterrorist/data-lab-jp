"""Write one deterministic private batch from the exact expansion insert set."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import os
from pathlib import Path
import sqlite3
import tempfile
from typing import Any

import revenue_mvp_expansion_d1_delta as delta_builder
from validate_affiliate_item_lookup_candidate import _snapshot_regular_file


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "runtime-candidates" / "affiliate-item-lookup-schema.sql"
VERSION = "0.1"
READY = "PRIVATE_INITIAL_SELECTION_READY"
BLOCKED = "BLOCKED"
BATCH_SIZE = 5


@dataclass(frozen=True)
class SelectionReceipt:
    version: str
    status: str
    inserted_scope_count: int
    selected_count: int
    batch_index: int
    batch_count: int
    output_sha256: str | None
    output_written: bool
    identifiers_exposed: bool
    api_request_performed: bool
    d1_write_performed: bool
    activation_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _blocked(reason: str) -> SelectionReceipt:
    return SelectionReceipt(
        VERSION, BLOCKED, 0, 0, 0, 0, None, False, False,
        False, False, False, (reason,),
    )


def build(
    before: bytes, after: bytes, schema: bytes, *, batch_index: Any,
    current: bytes | None = None,
) -> tuple[SelectionReceipt, bytes | None]:
    connections: list[sqlite3.Connection] = []
    try:
        if type(batch_index) is not int or batch_index < 0:
            return _blocked("BATCH_INDEX_INVALID"), None
        states: list[dict[str, tuple[Any, ...]]] = []
        for payload in (before, after):
            connection = sqlite3.connect(":memory:")
            connections.append(connection)
            delta_builder.load_remote_snapshot(connection, schema, payload)
            states.append({row[0]: row for row in connection.execute(
                """SELECT public_id,content_id,rights_status,lifecycle_status,
                          verification_status,affiliate_enabled
                   FROM affiliate_item_lookup"""
            )})
        before_rows, after_rows = states
        inserted = sorted(set(after_rows) - set(before_rows))
        if len(inserted) != 178 or any(
            after_rows[value][2:] != (
                "PENDING_SEPARATE_POLICY", "PENDING_OFFICIAL_CONFIRMATION", "PENDING", 0
            ) for value in inserted
        ):
            return _blocked("INSERTED_SCOPE_INVALID"), None
        batch_count = (len(inserted) + BATCH_SIZE - 1) // BATCH_SIZE
        if batch_index >= batch_count:
            return _blocked("BATCH_INDEX_OUT_OF_RANGE"), None
        selectable = inserted
        current_scope_verified = False
        if current is not None:
            connection = sqlite3.connect(":memory:")
            connections.append(connection)
            delta_builder.load_remote_snapshot(connection, schema, current)
            current_rows = {row[0]: row for row in connection.execute(
                """SELECT public_id,content_id,rights_status,lifecycle_status,
                          verification_status,affiliate_enabled
                   FROM affiliate_item_lookup"""
            )}
            allowed_states = {
                ("PENDING_SEPARATE_POLICY", "PENDING_OFFICIAL_CONFIRMATION", "PENDING", 0),
                ("CONDITIONALLY_APPROVED", "RESOLVED", "PASS", 1),
                ("CONDITIONALLY_APPROVED", "RESOLVED", "PENDING", 0),
            }
            if any(
                value not in current_rows
                or current_rows[value][1] != after_rows[value][1]
                or current_rows[value][2:] not in allowed_states
                for value in inserted
            ):
                return _blocked("CURRENT_SCOPE_INVALID"), None
            selectable = [
                value for value in inserted
                if current_rows[value][2:] == (
                    "PENDING_SEPARATE_POLICY", "PENDING_OFFICIAL_CONFIRMATION", "PENDING", 0
                )
            ]
            current_scope_verified = True
            batch_count = (len(selectable) + BATCH_SIZE - 1) // BATCH_SIZE
            if batch_index >= batch_count:
                return _blocked("BATCH_INDEX_OUT_OF_RANGE"), None
        selected = selectable[batch_index * BATCH_SIZE:(batch_index + 1) * BATCH_SIZE]
        payload = ("\n".join(selected) + "\n").encode("ascii")
        return SelectionReceipt(
            VERSION, READY, len(inserted), len(selected), batch_index,
            batch_count, hashlib.sha256(payload).hexdigest(), False, False,
            False, False, False,
            (
                "CURRENT_PENDING_SCOPE_VERIFIED" if current_scope_verified else "EXACT_INSERTED_SCOPE",
                "PRIVATE_SELECTION_ONLY", "LIVE_APPROVAL_REQUIRED",
            ),
        ), payload
    except Exception:
        return _blocked("SELECTION_BUILD_FAILED"), None
    finally:
        for connection in connections:
            connection.close()


def write(
    before: Path, after: Path, output: Path, *, batch_index: int,
    current: Path | None = None,
) -> SelectionReceipt:
    temporary: Path | None = None
    try:
        try:
            output.resolve().relative_to(ROOT.resolve())
            return _blocked("OUTPUT_MUST_BE_OUTSIDE_REPOSITORY")
        except ValueError:
            pass
        checked_paths = (before, after, output, SCHEMA) + ((current,) if current is not None else ())
        if any(path.is_symlink() for path in checked_paths) or output.exists():
            return _blocked("PATH_BOUNDARY_INVALID")
        receipt, payload = build(
            _snapshot_regular_file(before), _snapshot_regular_file(after),
            _snapshot_regular_file(SCHEMA), batch_index=batch_index,
            current=_snapshot_regular_file(current) if current is not None else None,
        )
        if receipt.status != READY or payload is None:
            return receipt
        output.parent.mkdir(parents=True, exist_ok=True)
        handle = tempfile.NamedTemporaryFile(
            mode="wb", dir=output.parent, prefix=".selection-", suffix=".tmp", delete=False
        )
        temporary = Path(handle.name)
        with handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o600)
        os.replace(temporary, output)
        temporary = None
        return SelectionReceipt(**{**asdict(receipt), "output_written": True})
    except (OSError, RuntimeError):
        return _blocked("FILESYSTEM_OPERATION_FAILED")
    finally:
        if temporary is not None and temporary.exists():
            try:
                temporary.unlink()
            except OSError:
                pass


__all__ = ["SelectionReceipt", "build", "write"]
