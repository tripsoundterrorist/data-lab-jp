"""Write one private, bounded selection from an exact product refresh delta."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.1"
READY = "PRIVATE_PRODUCT_REFRESH_SELECTION_READY"
BLOCKED = "BLOCKED"
BATCH_SIZE = 5
EXPECTED_SURFACE_COUNT = 100
EXPECTED_DELTA_COUNT = 18
ROUTE_PATTERN = re.compile(rb'href="/go/(itm_[0-9a-f]{24})"')


@dataclass(frozen=True)
class SelectionReceipt:
    version: str
    status: str
    source_count: int
    candidate_count: int
    added_count: int
    removed_count: int
    selected_count: int
    batch_index: int
    batch_count: int
    source_sha256: str | None
    candidate_sha256: str | None
    output_sha256: str | None
    output_written: bool
    identifiers_exposed: bool
    api_request_performed: bool
    d1_write_performed: bool
    publication_allowed: bool
    explicit_live_approval_required: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _blocked(reason: str) -> SelectionReceipt:
    return SelectionReceipt(
        VERSION, BLOCKED, 0, 0, 0, 0, 0, 0, 0, None, None, None,
        False, False, False, False, False, True, (reason,),
    )


def build(
    source: bytes, candidate: bytes, *, batch_index: Any,
) -> tuple[SelectionReceipt, bytes | None]:
    try:
        if type(batch_index) is not int or batch_index < 0:
            return _blocked("BATCH_INDEX_INVALID"), None
        source_ids = set(ROUTE_PATTERN.findall(source))
        candidate_ids = set(ROUTE_PATTERN.findall(candidate))
        if len(source_ids) != EXPECTED_SURFACE_COUNT:
            return _blocked("SOURCE_SCOPE_INVALID"), None
        if len(candidate_ids) != EXPECTED_SURFACE_COUNT:
            return _blocked("CANDIDATE_SCOPE_INVALID"), None
        added = sorted(candidate_ids - source_ids)
        removed = source_ids - candidate_ids
        if len(added) != EXPECTED_DELTA_COUNT or len(removed) != EXPECTED_DELTA_COUNT:
            return _blocked("REFRESH_DELTA_INVALID"), None
        batch_count = (len(added) + BATCH_SIZE - 1) // BATCH_SIZE
        if batch_index >= batch_count:
            return _blocked("BATCH_INDEX_OUT_OF_RANGE"), None
        selected = added[batch_index * BATCH_SIZE:(batch_index + 1) * BATCH_SIZE]
        payload = b"\n".join(selected) + b"\n"
        return SelectionReceipt(
            VERSION, READY, len(source_ids), len(candidate_ids), len(added),
            len(removed), len(selected), batch_index, batch_count,
            hashlib.sha256(source).hexdigest(),
            hashlib.sha256(candidate).hexdigest(),
            hashlib.sha256(payload).hexdigest(), False, False, False, False,
            False, True,
            (
                "EXACT_REFRESH_DELTA",
                "PRIVATE_SELECTION_ONLY",
                "LIVE_REVALIDATION_APPROVAL_REQUIRED",
            ),
        ), payload
    except (TypeError, ValueError):
        return _blocked("SELECTION_BUILD_FAILED"), None


def write(
    source: Path, candidate: Path, output: Path, *, batch_index: int,
) -> SelectionReceipt:
    temporary: Path | None = None
    try:
        try:
            output.resolve().relative_to(ROOT.resolve())
            return _blocked("OUTPUT_MUST_BE_OUTSIDE_REPOSITORY")
        except ValueError:
            pass
        if any(path.is_symlink() for path in (source, candidate, output)) or output.exists():
            return _blocked("PATH_BOUNDARY_INVALID")
        receipt, payload = build(
            source.read_bytes(), candidate.read_bytes(), batch_index=batch_index,
        )
        if receipt.status != READY or payload is None:
            return receipt
        output.parent.mkdir(parents=True, exist_ok=True)
        handle = tempfile.NamedTemporaryFile(
            mode="wb", dir=output.parent, prefix=".refresh-selection-",
            suffix=".tmp", delete=False,
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
    except OSError:
        return _blocked("FILESYSTEM_OPERATION_FAILED")
    finally:
        if temporary is not None and temporary.exists():
            try:
                temporary.unlink()
            except OSError:
                pass


__all__ = ["SelectionReceipt", "build", "write"]


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(
        description="Write one private product-refresh revalidation selection."
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--batch-index", type=int, required=True)
    args = parser.parse_args()
    result = write(
        args.source, args.candidate, args.output, batch_index=args.batch_index,
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == READY else 2


if __name__ == "__main__":
    raise SystemExit(main())
