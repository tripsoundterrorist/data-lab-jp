from dataclasses import replace
from pathlib import Path
import json
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import temporal_filesystem_state_connection_review as review  # noqa: E402


def complete_evidence():
    return review.FilesystemStateConnectionEvidence(
        version=review.VERSION,
        selected_target=review.SELECTED_TARGET,
        prerequisites_verified=True,
        trust_boundary_verified=True,
        rollback_recovery_verified=True,
        secret_pii_controls_verified=True,
        idempotency_verified=True,
        rate_cost_bounds_verified=True,
        publication_compliance_separation_verified=True,
        explicit_approval_point_defined=True,
        explicit_approval_granted=False,
    )


class FilesystemStateConnectionReviewTests(unittest.TestCase):
    def test_complete_evidence_is_ready_only_for_explicit_approval(self):
        result = review.review_filesystem_state_connection(complete_evidence())
        self.assertEqual(result.status, review.REVIEW_READY_FOR_EXPLICIT_APPROVAL)
        self.assertEqual(result.selected_target, "FILESYSTEM_BACKED_STATE")
        self.assertEqual(result.unmet_areas, ())
        self.assertFalse(result.connection_authorized)
        self.assertFalse(result.write_authorized)
        self.assertFalse(result.deploy_allowed)

    def test_every_missing_area_fails_closed(self):
        fields = (
            "prerequisites_verified", "trust_boundary_verified",
            "rollback_recovery_verified", "secret_pii_controls_verified",
            "idempotency_verified", "rate_cost_bounds_verified",
            "publication_compliance_separation_verified",
            "explicit_approval_point_defined",
        )
        for field in fields:
            with self.subTest(field=field):
                result = review.review_filesystem_state_connection(
                    replace(complete_evidence(), **{field: False})
                )
                self.assertEqual(result.status, review.REVIEW_BLOCKED)
                self.assertFalse(result.connection_authorized)

    def test_unknown_missing_or_contradictory_input_fails_closed(self):
        cases = (
            None,
            {},
            replace(complete_evidence(), version="unknown"),
            replace(complete_evidence(), selected_target="ACTIVE_PIPELINE"),
            replace(complete_evidence(), prerequisites_verified=1),
            replace(complete_evidence(), explicit_approval_granted=True),
        )
        for value in cases:
            with self.subTest(value=value):
                result = review.review_filesystem_state_connection(value)
                self.assertEqual(result.status, review.REVIEW_BLOCKED)
                self.assertFalse(result.write_authorized)
                self.assertFalse(result.deploy_allowed)

    def test_output_is_bounded_and_contains_no_evidence_values(self):
        encoded = json.dumps(
            review.review_filesystem_state_connection(complete_evidence()).to_dict()
        )
        self.assertNotIn("prerequisites_verified", encoded)
        self.assertNotIn("explicit_approval_granted", encoded)

    def test_cli_requires_caller_evidence_and_fails_closed(self):
        result = subprocess.run(
            [sys.executable, str(Path(review.__file__))],
            capture_output=True, text=True, check=False,
        )
        payload = json.loads(result.stdout)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(payload["status"], review.REVIEW_BLOCKED)
        self.assertFalse(payload["connection_authorized"])

    def test_source_has_no_external_or_filesystem_operation(self):
        source = Path(review.__file__).read_text(encoding="utf-8")
        for forbidden in (
            "open(", "read_text(", "read_bytes(", "write_text(",
            "write_bytes(", "mkdir(", "unlink(", "requests", "urllib",
            "subprocess", "run_dry_connection_harness(",
            "build_validated_series_state_bundle(", "plan_series_state_write(",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
