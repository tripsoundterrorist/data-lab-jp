from dataclasses import replace
import json
from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_control_center_evidence_sync as sync  # noqa: E402


class RevenueMvpControlCenterEvidenceSyncTests(unittest.TestCase):
    def evidence(self, **changes):
        return replace(sync.current_tracked_evidence(), **changes)

    def test_tracked_state_reflects_response_but_keeps_concrete_blockers(self):
        result = sync.current_sync()
        self.assertEqual(result.status, sync.SYNCED_BLOCKED)
        self.assertFalse(result.official_response_pending)
        self.assertEqual(result.official_response_scope, sync.REDUCED_SURFACE_ONLY)
        self.assertTrue(result.reduced_surface_review_candidate)
        self.assertTrue(result.full_surface_official_confirmation_pending)
        self.assertTrue(result.lifecycle_pipeline_verified)
        self.assertEqual(
            set(result.blocker_codes),
            {
                "SOURCE_DB_AND_PUBLIC_ARTIFACT_REVALIDATION_REQUIRED",
                "PRODUCTION_D1_READ_ONLY_RECONFIRMATION_REQUIRED",
                "REDUCED_SURFACE_MANUAL_GATE_REVIEW_REQUIRED",
            },
        )
        self.assertEqual(
            result.next_action, "REVALIDATE_SOURCE_DB_AND_PUBLIC_ARTIFACT"
        )

    def test_confirmed_operational_evidence_reaches_review_only_not_ready(self):
        result = sync.synchronize_control_center_evidence(
            self.evidence(
                source_db_artifact_binding_verified=True,
                production_d1_read_only_reconfirmed=True,
                manual_reduced_surface_gate_approved=True,
            )
        )
        self.assertEqual(result.status, sync.REVIEW_CANDIDATE)
        self.assertEqual(result.next_action, "REVIEW_SEPARATE_PUBLICATION_GATE")
        self.assertEqual(result.blocker_codes, ())
        self.assertFalse(result.publication_allowed)
        self.assertFalse(result.production_activation_allowed)
        self.assertFalse(result.affiliate_eligibility_allowed)
        self.assertFalse(result.gate_mutation_allowed)

    def test_missing_official_response_is_distinct_and_fail_closed(self):
        result = sync.synchronize_control_center_evidence(
            self.evidence(official_response_received_on=None)
        )
        self.assertEqual(result.status, sync.FAIL_CLOSED)
        self.assertTrue(result.official_response_pending)
        self.assertEqual(
            result.blocker_codes, ("OFFICIAL_RESPONSE_EVIDENCE_REQUIRED",)
        )
        self.assertEqual(
            result.next_action, "INTAKE_VERSIONED_OFFICIAL_RESPONSE_EVIDENCE"
        )

    def test_version_scope_or_mapping_mismatch_fails_closed(self):
        cases = (
            {"evidence_version": "unknown"},
            {"official_response_scope": "FULL_SURFACE"},
            {"official_policy_version": "unknown"},
            {"reduced_surface_mapping_status": "READY"},
            {"bounded_runner_version": "unknown"},
        )
        for changes in cases:
            with self.subTest(changes=changes):
                result = sync.synchronize_control_center_evidence(
                    self.evidence(**changes)
                )
                self.assertEqual(result.status, sync.FAIL_CLOSED)
                self.assertTrue(result.official_response_pending)
                self.assertIn(
                    "CONTROL_CENTER_EVIDENCE_VERSION_OR_SCOPE_MISMATCH",
                    result.blocker_codes,
                )

    def test_pipeline_evidence_is_independent_from_operational_proof(self):
        result = sync.synchronize_control_center_evidence(
            self.evidence(builder_prefilter_verified=False)
        )
        self.assertEqual(result.status, sync.SYNCED_BLOCKED)
        self.assertFalse(result.lifecycle_pipeline_verified)
        self.assertIn(
            "LIFECYCLE_PIPELINE_EVIDENCE_INCOMPLETE", result.blocker_codes
        )
        self.assertEqual(
            result.next_action, "COMPLETE_LIFECYCLE_PIPELINE_EVIDENCE_REVIEW"
        )

    def test_reduced_scope_cannot_overclaim_full_surface_confirmation(self):
        result = sync.synchronize_control_center_evidence(
            self.evidence(full_surface_official_confirmation_received=True)
        )
        self.assertEqual(result.status, sync.FAIL_CLOSED)
        self.assertTrue(result.full_surface_official_confirmation_pending)
        self.assertIn("FULL_SURFACE_EVIDENCE_OUT_OF_SCOPE", result.blocker_codes)
        self.assertFalse(result.publication_allowed)

    def test_non_boolean_and_unknown_input_fail_closed(self):
        malformed = sync.synchronize_control_center_evidence(
            self.evidence(production_d1_read_only_reconfirmed=1)
        )
        self.assertEqual(malformed.status, sync.FAIL_CLOSED)
        self.assertIn("CONTROL_CENTER_EVIDENCE_MALFORMED", malformed.blocker_codes)
        missing = sync.synchronize_control_center_evidence(None)
        self.assertEqual(missing.status, sync.FAIL_CLOSED)
        self.assertIn("CONTROL_CENTER_EVIDENCE_REQUIRED", missing.blocker_codes)

    def test_output_is_sanitized_and_source_has_no_external_io(self):
        rendered = json.dumps(sync.current_sync().to_dict()).casefold()
        for forbidden in (
            "content_id",
            "public_id",
            "https://",
            "api_id",
            "affiliate_id",
            "database_sha",
            "raw_response",
            "credential",
        ):
            self.assertNotIn(forbidden, rendered)
        source = Path(sync.__file__).read_text(encoding="utf-8")
        for forbidden in (
            "open(",
            "read_text(",
            "write_text(",
            "sqlite3",
            "requests",
            "urllib",
            "subprocess",
            "os.environ",
        ):
            self.assertNotIn(forbidden, source)

    def test_current_blocked_cli_returns_nonzero(self):
        with mock.patch("builtins.print"):
            self.assertEqual(sync.main(), 2)


if __name__ == "__main__":
    unittest.main()
