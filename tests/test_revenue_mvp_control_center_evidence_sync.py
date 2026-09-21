from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_control_center_evidence_sync as sync  # noqa: E402


class RevenueMvpControlCenterEvidenceSyncTests(unittest.TestCase):
    def setUp(self):
        self.baseline = sync.load_reviewed_baseline()
        self.assertIsNotNone(self.baseline)
        self.current = sync.collect_current_evidence(self.baseline)

    def with_hash(self, path, digest):
        hashes = dict(self.current.current_evidence_sha256)
        hashes[path] = digest
        return replace(self.current, current_evidence_sha256=tuple(sorted(hashes.items())))

    def test_manifest_is_fixed_to_reviewed_commit_versions_paths_and_digest(self):
        self.assertEqual(self.baseline.reviewed_base_ref, "main")
        self.assertEqual(
            self.baseline.reviewed_base_commit,
            "f637829b080e0a95a03e3a8880935553c9fbfcb7",
        )
        self.assertEqual(self.baseline.manifest_version, "0.2")
        self.assertEqual(
            tuple(path for path, _digest in self.baseline.required_evidence_sha256),
            sync.REQUIRED_EVIDENCE_PATHS,
        )
        self.assertEqual(
            self.baseline.builder_prefilter_evidence_paths,
            sync.BUILDER_PREFILTER_PATHS,
        )
        self.assertEqual(
            self.baseline.saved_receipt_evidence_paths,
            sync.SAVED_RECEIPT_PATHS,
        )
        self.assertEqual(
            sync._baseline_digest(self.baseline), sync.BASELINE_MANIFEST_SHA256
        )

    def test_current_state_matches_baseline_but_keeps_operational_blockers(self):
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

    def test_unreviewed_lifecycle_contract_version_fails_closed(self):
        current = replace(
            self.current,
            current_versions=tuple(sorted({
                **dict(self.current.current_versions),
                "lifecycle_receipt": "unknown",
            }.items())),
        )
        result = sync.evaluate_control_center_evidence(self.baseline, current)
        self.assertEqual(result.status, sync.FAIL_CLOSED)
        self.assertEqual(result.blocker_codes, ("TRACKED_EVIDENCE_VERSION_MISMATCH",))
        self.assertEqual(result.reason_codes, ("UNREVIEWED_CONTRACT_VERSION_DETECTED",))

    def test_unknown_contract_versions_fail_closed(self):
        cases = (
            (sync.lifecycle_policy, "POLICY_VERSION"),
            (sync.bounded_runner, "RUNNER_VERSION"),
            (sync.lifecycle_receipt, "LIFECYCLE_RECEIPT_VERSION"),
        )
        for module, attribute in cases:
            with self.subTest(attribute=attribute), mock.patch.object(
                module, attribute, "unknown"
            ):
                current = sync.collect_current_evidence(self.baseline)
                result = sync.evaluate_control_center_evidence(
                    self.baseline, current
                )
                self.assertEqual(result.status, sync.FAIL_CLOSED)
                self.assertTrue(result.official_response_pending)
                self.assertFalse(result.lifecycle_pipeline_verified)
                self.assertEqual(
                    result.blocker_codes, ("TRACKED_EVIDENCE_VERSION_MISMATCH",)
                )

    def test_each_required_path_missing_fails_closed(self):
        for path in sync.REQUIRED_EVIDENCE_PATHS:
            with self.subTest(path=path):
                current = replace(self.current, missing_paths=(path,))
                result = sync.evaluate_control_center_evidence(
                    self.baseline, current
                )
                self.assertEqual(result.status, sync.FAIL_CLOSED)
                self.assertTrue(result.official_response_pending)
                self.assertEqual(
                    result.blocker_codes, ("TRACKED_EVIDENCE_PATH_MISSING",)
                )

    def test_general_hash_mismatch_fails_closed(self):
        path = "scripts/revenue_mvp_offline_lifecycle_filter.py"
        result = sync.evaluate_control_center_evidence(
            self.baseline, self.with_hash(path, "0" * 64)
        )
        self.assertEqual(result.status, sync.FAIL_CLOSED)
        self.assertTrue(result.official_response_pending)
        self.assertEqual(result.blocker_codes, ("TRACKED_EVIDENCE_HASH_MISMATCH",))

    def test_builder_and_saved_receipt_bindings_fail_independently(self):
        cases = (
            (sync.BUILDER_PREFILTER_PATHS[0], "BUILDER_PREFILTER_BINDING_MISMATCH"),
            (sync.SAVED_RECEIPT_PATHS[0], "SAVED_RECEIPT_BINDING_MISMATCH"),
        )
        for path, blocker in cases:
            with self.subTest(path=path):
                result = sync.evaluate_control_center_evidence(
                    self.baseline, self.with_hash(path, "0" * 64)
                )
                self.assertEqual(result.status, sync.FAIL_CLOSED)
                self.assertEqual(result.blocker_codes, (blocker,))

    def test_malformed_and_tampered_manifests_fail_closed(self):
        self.assertIsNone(sync.parse_reviewed_baseline({}))
        tampered = replace(self.baseline, reviewed_base_commit="0" * 40)
        result = sync.evaluate_control_center_evidence(tampered, self.current)
        self.assertEqual(result.status, sync.FAIL_CLOSED)
        self.assertTrue(result.official_response_pending)
        self.assertEqual(
            result.blocker_codes, ("REVIEWED_BASELINE_MANIFEST_INVALID",)
        )
        wrong_ref = replace(self.baseline, reviewed_base_ref="not-main")
        result = sync.evaluate_control_center_evidence(wrong_ref, self.current)
        self.assertEqual(result.status, sync.FAIL_CLOSED)
        self.assertEqual(
            result.blocker_codes, ("REVIEWED_BASELINE_MANIFEST_INVALID",)
        )

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "baseline.json"
            payload = json.loads(sync.BASELINE_PATH.read_text(encoding="utf-8"))
            payload["expected_versions"]["bounded_runner"] = "tampered"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with mock.patch.object(sync, "BASELINE_PATH", path):
                self.assertIsNone(sync.load_reviewed_baseline())
                current_result = sync.current_sync()
        self.assertEqual(current_result.status, sync.FAIL_CLOSED)
        self.assertTrue(current_result.official_response_pending)

    def test_all_operational_evidence_reaches_review_candidate_only(self):
        current = replace(
            self.current,
            source_db_artifact_binding_verified=True,
            production_d1_read_only_reconfirmed=True,
            manual_reduced_surface_gate_approved=True,
        )
        result = sync.evaluate_control_center_evidence(self.baseline, current)
        self.assertEqual(result.status, sync.REVIEW_CANDIDATE)
        self.assertEqual(result.blocker_codes, ())
        self.assertEqual(result.next_action, "REVIEW_SEPARATE_PUBLICATION_GATE")
        self.assertFalse(result.publication_allowed)
        self.assertFalse(result.production_activation_allowed)
        self.assertFalse(result.affiliate_eligibility_allowed)
        self.assertFalse(result.gate_mutation_allowed)

    def test_full_surface_overclaim_and_non_boolean_fail_closed(self):
        overclaim = replace(
            self.current, full_surface_official_confirmation_received=True
        )
        result = sync.evaluate_control_center_evidence(self.baseline, overclaim)
        self.assertEqual(result.status, sync.FAIL_CLOSED)
        self.assertFalse(result.official_response_pending)
        self.assertIn("FULL_SURFACE_EVIDENCE_OUT_OF_SCOPE", result.blocker_codes)

        malformed = replace(
            self.current,
            production_d1_read_only_reconfirmed=1,
        )
        result = sync.evaluate_control_center_evidence(self.baseline, malformed)
        self.assertEqual(result.status, sync.FAIL_CLOSED)
        self.assertTrue(result.official_response_pending)
        self.assertEqual(
            result.blocker_codes, ("CURRENT_TRACKED_EVIDENCE_MALFORMED",)
        )

    def test_permissions_remain_false_for_all_outcomes(self):
        review_current = replace(
            self.current,
            source_db_artifact_binding_verified=True,
            production_d1_read_only_reconfirmed=True,
            manual_reduced_surface_gate_approved=True,
        )
        outcomes = (
            sync.evaluate_control_center_evidence(self.baseline, self.current),
            sync.evaluate_control_center_evidence(self.baseline, review_current),
            sync.evaluate_control_center_evidence(None, self.current),
        )
        for result in outcomes:
            with self.subTest(status=result.status):
                self.assertFalse(result.publication_allowed)
                self.assertFalse(result.production_activation_allowed)
                self.assertFalse(result.affiliate_eligibility_allowed)
                self.assertFalse(result.gate_mutation_allowed)

    def test_output_is_sanitized_and_collector_is_read_only(self):
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
            "write_text(",
            "write_bytes(",
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
