import json
from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_deployment_preflight as preflight  # noqa: E402


def artifact_result(*, validation="PASS", allowed=False, reasons=()):
    return SimpleNamespace(
        artifact_validation=validation,
        publication_allowed=allowed,
        item_count=2,
        shard_count=2,
        reason_codes=reasons,
    )


class RevenueMvpDeploymentPreflightTests(unittest.TestCase):
    def test_current_shell_is_validated_without_data_permission(self):
        result = preflight.run_preflight()
        self.assertEqual(result.status, preflight.SHELL_VALIDATED)
        self.assertEqual(result.production_build, "PASS")
        self.assertEqual(result.deployment_preflight, "NOT_EVALUATED_NO_PUBLIC_DATA")
        self.assertEqual(result.public_data_state, "UNPUBLISHED")
        self.assertFalse(result.public_data_deployment_allowed)
        self.assertEqual(result.shell_file_count, 20)

    def test_candidate_with_closed_publication_gate_is_blocked(self):
        with tempfile.TemporaryDirectory() as temporary:
            (Path(temporary) / "manifest.json").write_text("{}", encoding="utf-8")
            with mock.patch.object(
                preflight, "validate_artifacts",
                return_value=artifact_result(reasons=("LIFECYCLE_GATE_PENDING",)),
            ):
                result = preflight.run_preflight(
                    artifact_directory=Path(temporary)
                )
        self.assertEqual(result.status, preflight.BLOCKED)
        self.assertEqual(result.deployment_preflight, "CLOSED")
        self.assertFalse(result.public_data_deployment_allowed)
        self.assertIn("PUBLIC_DATA_GATE_CLOSED", result.reason_codes)

    def test_only_fully_allowed_candidate_passes_deployment_preflight(self):
        with tempfile.TemporaryDirectory() as temporary:
            (Path(temporary) / "manifest.json").write_text("{}", encoding="utf-8")
            with mock.patch.object(
                preflight, "validate_artifacts",
                return_value=artifact_result(allowed=True),
            ):
                result = preflight.run_preflight(
                    artifact_directory=Path(temporary)
                )
        self.assertEqual(result.status, preflight.READY)
        self.assertEqual(result.deployment_preflight, "PASS")
        self.assertTrue(result.public_data_deployment_allowed)

    def test_failed_artifact_validation_is_blocked(self):
        with tempfile.TemporaryDirectory() as temporary:
            (Path(temporary) / "bad.json").write_text("{", encoding="utf-8")
            result = preflight.run_preflight(artifact_directory=Path(temporary))
        self.assertEqual(result.status, preflight.BLOCKED)
        self.assertIn("ARTIFACT_VALIDATION_FAILED", result.reason_codes)
        self.assertFalse(result.public_data_deployment_allowed)

    def test_non_temp_artifact_directory_fails_closed_without_path_echo(self):
        result = preflight.run_preflight(artifact_directory=ROOT)
        serialized = json.dumps(result.to_dict())
        self.assertEqual(result.status, preflight.FAIL_CLOSED)
        self.assertNotIn(str(ROOT), serialized)

    def test_cli_shell_validation_is_non_deploying_and_successful(self):
        process = subprocess.run(
            [sys.executable, str(ROOT / "scripts/revenue_mvp_deployment_preflight.py")],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        result = json.loads(process.stdout)
        self.assertEqual(result["status"], preflight.SHELL_VALIDATED)
        self.assertFalse(result["public_data_deployment_allowed"])
        self.assertNotIn(str(ROOT), process.stdout)


if __name__ == "__main__":
    unittest.main()
