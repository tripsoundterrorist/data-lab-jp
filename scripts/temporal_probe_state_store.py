"""Filesystem adapter for local-only temporal probe states.

Only validated serialized states may be written, and only below the ignored
``logs/probes/state`` directory. This module contains no API or DB access.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
from typing import Any
import uuid

from temporal_probe_state import (
    TemporalProbeState,
    deserialize_temporal_probe_state,
    serialize_temporal_probe_state,
    validate_temporal_probe_state,
)


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STATE_DIRECTORY = REPOSITORY_ROOT / "logs" / "probes" / "state"
STATE_FILENAME = re.compile(
    r"(?:rank|review)-offset[0-9]{6}-hits[0-9]{3,6}-[0-9]{8}T[0-9]{12}Z\.json\Z"
)
MAX_STATE_BYTES = 1024 * 1024


@dataclass(frozen=True)
class StoreResult:
    success: bool
    idempotent: bool
    conflict: bool
    reason_codes: tuple[str, ...]
    filename: str | None = None
    sha256: str | None = None
    read_back_valid: bool = False


@dataclass(frozen=True)
class DiscoveryResult:
    success: bool
    reason_codes: tuple[str, ...]
    state: TemporalProbeState | None = None
    valid_candidates: int = 0


def _is_symlink(path: Path) -> bool:
    return path.is_symlink()


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _safe_output_directory(path: Any, *, must_exist: bool) -> tuple[Path | None, str | None]:
    try:
        if not isinstance(path, Path) or not path.is_absolute():
            return None, "UNSAFE_OUTPUT_DIRECTORY"
        root = REPOSITORY_ROOT.resolve()
        allowed = DEFAULT_STATE_DIRECTORY.resolve(strict=False)
        resolved = path.resolve(strict=False)
        if resolved == root or not _inside(resolved, allowed):
            return None, "UNSAFE_OUTPUT_DIRECTORY"
        current = root
        for part in resolved.relative_to(root).parts:
            current = current / part
            if current.exists() and _is_symlink(current):
                return None, "SYMLINK_OUTPUT_FORBIDDEN"
        if must_exist and (not resolved.is_dir() or _is_symlink(resolved)):
            return None, "OUTPUT_DIRECTORY_UNAVAILABLE"
        return resolved, None
    except (OSError, RuntimeError):
        return None, "UNSAFE_OUTPUT_DIRECTORY"


def safe_state_filename(state: TemporalProbeState) -> str:
    validation = validate_temporal_probe_state(state)
    if not validation.valid:
        raise ValueError("invalid state")
    captured = state.captured_at.astimezone(timezone.utc).strftime(
        "%Y%m%dT%H%M%S%fZ"
    )
    filename = (
        f"{state.source_sort}-offset{state.offset:06d}-"
        f"hits{state.hits:03d}-{captured}.json"
    )
    if STATE_FILENAME.fullmatch(filename) is None:
        raise ValueError("unsafe filename")
    return filename


def safe_child_path(directory: Path, filename: str) -> Path:
    if (
        not isinstance(filename, str)
        or STATE_FILENAME.fullmatch(filename) is None
        or Path(filename).name != filename
        or Path(filename).is_absolute()
    ):
        raise ValueError("unsafe filename")
    candidate = directory / filename
    if candidate.parent != directory:
        raise ValueError("unsafe filename")
    return candidate


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _serialized_bytes(state: Any) -> bytes:
    return (serialize_temporal_probe_state(state) + "\n").encode("utf-8")


def plan_state_write(
    state: Any, *, output_directory: Path = DEFAULT_STATE_DIRECTORY
) -> StoreResult:
    """Validate and return a plan without mkdir, write, delete, or rename."""

    try:
        validation = validate_temporal_probe_state(state)
        if not validation.valid:
            return StoreResult(False, False, False, validation.reason_codes)
        directory, error = _safe_output_directory(output_directory, must_exist=False)
        if error or directory is None:
            return StoreResult(False, False, False, (error or "UNSAFE_OUTPUT_DIRECTORY",))
        filename = safe_state_filename(state)
        content = _serialized_bytes(state)
        return StoreResult(
            True, False, False, (), filename=filename, sha256=_sha256(content)
        )
    except Exception:
        return StoreResult(False, False, False, ("INTERNAL_STORE_ERROR",))


def _read_regular_file(path: Path) -> bytes:
    if _is_symlink(path) or not path.is_file():
        raise OSError("not a regular state file")
    if path.stat().st_size > MAX_STATE_BYTES:
        raise OSError("state file too large")
    return path.read_bytes()


def write_temporal_probe_state(
    state: Any, *, output_directory: Path = DEFAULT_STATE_DIRECTORY
) -> StoreResult:
    temporary_path: Path | None = None
    lock_path: Path | None = None
    lock_descriptor: int | None = None
    created_final_path: Path | None = None
    final_verified = False
    try:
        validation = validate_temporal_probe_state(state)
        if not validation.valid:
            return StoreResult(False, False, False, validation.reason_codes)
        directory, error = _safe_output_directory(output_directory, must_exist=True)
        if error or directory is None:
            return StoreResult(False, False, False, (error or "UNSAFE_OUTPUT_DIRECTORY",))
        filename = safe_state_filename(state)
        final_path = safe_child_path(directory, filename)
        content = _serialized_bytes(state)
        expected_hash = _sha256(content)

        if final_path.exists() or _is_symlink(final_path):
            if _is_symlink(final_path):
                return StoreResult(False, False, True, ("SYMLINK_TARGET_FORBIDDEN",))
            existing = _read_regular_file(final_path)
            if existing == content:
                parsed = deserialize_temporal_probe_state(existing.decode("utf-8"))
                return StoreResult(
                    parsed is not None,
                    parsed is not None,
                    False,
                    () if parsed is not None else ("READ_BACK_INVALID",),
                    filename=filename,
                    sha256=expected_hash,
                    read_back_valid=parsed is not None,
                )
            return StoreResult(False, False, True, ("STATE_CONFLICT",), filename)

        lock_path = directory / f".{filename}.lock"
        lock_descriptor = os.open(
            lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
        os.close(lock_descriptor)
        lock_descriptor = None
        if final_path.exists() or _is_symlink(final_path):
            return StoreResult(False, False, True, ("STATE_CONFLICT",), filename)

        temporary_path = directory / f".{filename}.{uuid.uuid4().hex}.tmp"
        with temporary_path.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, final_path)
        temporary_path = None
        created_final_path = final_path

        read_back = _read_regular_file(final_path)
        parsed = deserialize_temporal_probe_state(read_back.decode("utf-8"))
        if parsed is None or parsed != state or _sha256(read_back) != expected_hash:
            return StoreResult(
                False,
                False,
                False,
                ("READ_BACK_VALIDATION_FAILED",),
                filename,
                expected_hash,
                False,
            )
        final_verified = True
        return StoreResult(
            True, False, False, (), filename, expected_hash, True
        )
    except FileExistsError:
        return StoreResult(False, False, True, ("CONCURRENT_WRITE_CONFLICT",))
    except Exception:
        return StoreResult(False, False, False, ("INTERNAL_STORE_ERROR",))
    finally:
        if lock_descriptor is not None:
            os.close(lock_descriptor)
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except OSError:
                pass
        if created_final_path is not None and not final_verified:
            try:
                created_final_path.unlink()
            except OSError:
                pass
        if lock_path is not None:
            try:
                lock_path.unlink()
            except OSError:
                pass


def discover_valid_states(
    *, output_directory: Path = DEFAULT_STATE_DIRECTORY, as_of: datetime
) -> tuple[TemporalProbeState, ...]:
    directory, error = _safe_output_directory(output_directory, must_exist=True)
    if error or directory is None:
        return ()
    states: list[TemporalProbeState] = []
    try:
        for entry in os.scandir(directory):
            path = Path(entry.path)
            if (
                not entry.is_file(follow_symlinks=False)
                or entry.is_symlink()
                or STATE_FILENAME.fullmatch(entry.name) is None
            ):
                continue
            try:
                content = _read_regular_file(path)
                state = deserialize_temporal_probe_state(content.decode("utf-8"))
                if state is None:
                    continue
                validation = validate_temporal_probe_state(state, as_of=as_of)
                if validation.valid:
                    states.append(state)
            except (OSError, UnicodeError):
                continue
        return tuple(sorted(states, key=lambda value: value.captured_at))
    except Exception:
        return ()


def latest_previous_state(
    current: Any,
    *,
    output_directory: Path = DEFAULT_STATE_DIRECTORY,
    as_of: datetime,
) -> DiscoveryResult:
    try:
        validation = validate_temporal_probe_state(current, as_of=as_of)
        if not validation.valid:
            return DiscoveryResult(False, validation.reason_codes)
        candidates = [
            state
            for state in discover_valid_states(
                output_directory=output_directory, as_of=as_of
            )
            if state.population_identity == current.population_identity
            and state.captured_at < current.captured_at
        ]
        return DiscoveryResult(
            True,
            (),
            state=max(candidates, key=lambda value: value.captured_at)
            if candidates
            else None,
            valid_candidates=len(candidates),
        )
    except Exception:
        return DiscoveryResult(False, ("INTERNAL_DISCOVERY_ERROR",))


__all__ = [
    "DEFAULT_STATE_DIRECTORY",
    "DiscoveryResult",
    "StoreResult",
    "discover_valid_states",
    "latest_previous_state",
    "plan_state_write",
    "safe_child_path",
    "safe_state_filename",
    "write_temporal_probe_state",
]
