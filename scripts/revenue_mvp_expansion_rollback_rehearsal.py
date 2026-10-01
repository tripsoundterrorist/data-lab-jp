"""Isolated byte-exact rollback rehearsal for the live 100-item static surface."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from html.parser import HTMLParser
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
from typing import Any, Mapping


VERSION = "0.1"
VERIFIED = "ROLLBACK_REHEARSAL_VERIFIED"
FAIL_CLOSED = "ROLLBACK_REHEARSAL_FAIL_CLOSED"
ROOT = Path(__file__).resolve().parents[1]
EXPECTED_ITEM_COUNT = 100


def _load_builder() -> Any:
    path = ROOT / "scripts" / "build-static-site.py"
    specification = importlib.util.spec_from_file_location(
        "expansion_rollback_static_builder", path
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("builder unavailable")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


class _ItemCounter(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.count = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "article":
            return
        values = {key.casefold(): value or "" for key, value in attrs}
        if "item" in values.get("class", "").split():
            self.count += 1


@dataclass(frozen=True)
class RollbackRehearsal:
    version: str
    status: str
    source_file_count: int
    source_item_count: int
    source_snapshot_sha256: str | None
    candidate_differed_from_source: bool
    restore_byte_exact: bool
    repeated_restore_deterministic: bool
    source_unchanged: bool
    rollback_plan_verified: bool
    publication_allowed: bool
    deployment_allowed: bool
    external_io_performed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _snapshot_sha256(files: Mapping[str, bytes]) -> str:
    digest = hashlib.sha256()
    for name in sorted(files):
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(files[name])
    return digest.hexdigest()


def _read_tree(root: Path, names: tuple[str, ...]) -> dict[str, bytes]:
    return {name: (root / name).read_bytes() for name in names}


def _failed(reason: str) -> RollbackRehearsal:
    return RollbackRehearsal(
        VERSION, FAIL_CLOSED, 0, 0, None, False, False, False, False,
        False, False, False, False, (reason,),
    )


def rehearse(root: Path = ROOT) -> RollbackRehearsal:
    try:
        builder = _load_builder()
        resolved_root = builder.resolve_repo_root(root)
        source = builder.collect_sources(resolved_root)
        builder.validate_files(source, builder.read_known_secret_values(resolved_root))
        before = _snapshot_sha256(source)

        parser = _ItemCounter()
        parser.feed(source["items/index.html"].decode("utf-8"))
        parser.close()
        if parser.count != EXPECTED_ITEM_COUNT:
            return _failed("CURRENT_ITEM_COUNT_NOT_EXACT")

        candidate = dict(source)
        marker = "100件".encode("utf-8")
        if marker not in candidate["items/index.html"]:
            return _failed("CANDIDATE_SENTINEL_UNAVAILABLE")
        candidate["items/index.html"] = candidate["items/index.html"].replace(
            marker, "300件".encode("utf-8"), 1
        )
        builder.validate_files(
            candidate, builder.read_known_secret_values(resolved_root)
        )
        candidate_differed = _snapshot_sha256(candidate) != before
        if not candidate_differed:
            return _failed("CANDIDATE_DID_NOT_DIFFER")

        with tempfile.TemporaryDirectory(prefix="data-lab-expansion-rollback-") as directory:
            output = Path(directory) / "dist" / "surface"
            builder.atomic_publish(output, source)
            builder.atomic_publish(output, candidate)
            candidate_written = _read_tree(output, builder.ALLOWLIST)
            builder.atomic_publish(output, source)
            first_restore = _read_tree(output, builder.ALLOWLIST)
            builder.atomic_publish(output, source)
            second_restore = _read_tree(output, builder.ALLOWLIST)

        after_source = builder.collect_sources(resolved_root)
        restore_exact = first_restore == source
        repeated = second_restore == first_restore and _snapshot_sha256(second_restore) == before
        source_unchanged = after_source == source and _snapshot_sha256(after_source) == before
        verified = (
            candidate_written == candidate
            and candidate_differed
            and restore_exact
            and repeated
            and source_unchanged
        )
        return RollbackRehearsal(
            VERSION,
            VERIFIED if verified else FAIL_CLOSED,
            len(source),
            parser.count,
            before,
            candidate_differed,
            restore_exact,
            repeated,
            source_unchanged,
            verified,
            False,
            False,
            False,
            () if verified else ("ROLLBACK_REHEARSAL_MISMATCH",),
        )
    except Exception:
        return _failed("ROLLBACK_REHEARSAL_INTERNAL_ERROR")


def main() -> int:
    result = rehearse()
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == VERIFIED else 2


if __name__ == "__main__":
    raise SystemExit(main())
