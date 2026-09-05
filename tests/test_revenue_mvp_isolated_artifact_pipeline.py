from pathlib import Path
from types import SimpleNamespace
import json
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_isolated_artifact_pipeline as gate  # noqa: E402


STAMP = gate._timestamp("2026-09-05T00:00:00Z")


def handoff(ready=True):
    return SimpleNamespace(
        status="HANDOFF_READY" if ready else "BLOCKED",
        identity_verified=ready,
        reason_codes=("DB_HANDOFF_VERIFIED",) if ready else ("DATABASE_IDENTITY_MISMATCH",),
    )


def validation(valid=True):
    return SimpleNamespace(
        artifact_validation="PASS" if valid else "FAIL_CLOSED",
        item_count=2,
        shard_count=2,
        reason_codes=() if valid else ("FORBIDDEN_FIELD",),
    )


class Builder:
    def __init__(self):
        self.files = {
            "manifest.json": b"{}",
            "index.json": b"{}",
            "items/00/itm_000000000000000000000000.json": b"{}",
        }

    def build_documents(self, *_args):
        return self.files, {}

    def atomic_write(self, output, files):
        output.mkdir()
        for name, content in files.items():
            destination = output / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)


class IsolatedArtifactPipelineTests(unittest.TestCase):
    def test_verified_db_builds_new_temp_artifact_without_publication(self):
        builder = Builder()
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "candidate"
            with (
                mock.patch.object(gate.db_handoff, "preflight", return_value=handoff()),
                mock.patch.object(gate, "validate_artifacts", return_value=validation()),
            ):
                result = gate.run_pipeline(
                    Path("ignored.db"), "0" * 64, output,
                    as_of=STAMP, generated_at=STAMP,
                    load_builder=lambda: builder,
                )
            self.assertTrue(output.is_dir())
            self.assertEqual(
                set(gate._read_artifacts(output)),
                set(builder.files),
            )
        self.assertEqual(result.status, gate.LOCAL_ARTIFACT_VALIDATED)
        self.assertTrue(result.artifact_written)
        self.assertFalse(result.publication_allowed)
        self.assertFalse(result.production_write_performed)

    def test_database_failure_stops_before_builder(self):
        loader = mock.Mock()
        with tempfile.TemporaryDirectory() as temporary:
            with mock.patch.object(
                gate.db_handoff, "preflight", return_value=handoff(False)
            ):
                result = gate.run_pipeline(
                    Path("ignored.db"), "0" * 64, Path(temporary) / "candidate",
                    as_of=STAMP, generated_at=STAMP, load_builder=loader,
                )
        loader.assert_not_called()
        self.assertEqual(result.status, gate.BLOCKED)
        self.assertFalse(result.artifact_written)

    def test_in_memory_validation_failure_prevents_write(self):
        builder = Builder()
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "candidate"
            with (
                mock.patch.object(gate.db_handoff, "preflight", return_value=handoff()),
                mock.patch.object(gate, "validate_artifacts", return_value=validation(False)),
            ):
                result = gate.run_pipeline(
                    Path("ignored.db"), "0" * 64, output,
                    as_of=STAMP, generated_at=STAMP,
                    load_builder=lambda: builder,
                )
            self.assertFalse(output.exists())
        self.assertFalse(result.artifact_written)

    def test_database_change_after_build_prevents_write(self):
        builder = Builder()
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "candidate"
            with (
                mock.patch.object(
                    gate.db_handoff, "preflight",
                    side_effect=(handoff(), handoff(False)),
                ),
                mock.patch.object(gate, "validate_artifacts", return_value=validation()),
            ):
                result = gate.run_pipeline(
                    Path("ignored.db"), "0" * 64, output,
                    as_of=STAMP, generated_at=STAMP, load_builder=lambda: builder,
                )
            self.assertFalse(output.exists())
        self.assertIn("DATABASE_CHANGED_DURING_PIPELINE", result.reason_codes)

    def test_existing_or_non_temp_output_fails_closed_without_path_leak(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = gate.run_pipeline(
                Path("ignored.db"), "0" * 64, Path(temporary),
                as_of=STAMP, generated_at=STAMP,
            )
        serialized = json.dumps(result.to_dict())
        self.assertEqual(result.status, gate.FAIL_CLOSED)
        self.assertNotIn(temporary, serialized)
        outside = gate.run_pipeline(
            Path("ignored.db"), "0" * 64, ROOT / "candidate",
            as_of=STAMP, generated_at=STAMP,
        )
        self.assertEqual(outside.status, gate.FAIL_CLOSED)

    def test_internal_error_is_sanitized(self):
        with tempfile.TemporaryDirectory() as temporary:
            with mock.patch.object(
                gate.db_handoff, "preflight",
                side_effect=RuntimeError("secret path"),
            ):
                result = gate.run_pipeline(
                    Path("ignored.db"), "0" * 64,
                    Path(temporary) / "candidate",
                    as_of=STAMP, generated_at=STAMP,
                )
        self.assertNotIn("secret", json.dumps(result.to_dict()))


if __name__ == "__main__":
    unittest.main()
