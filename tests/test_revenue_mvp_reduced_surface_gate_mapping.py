from dataclasses import replace
from pathlib import Path
import json
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import official_blocker_policy as blockers  # noqa: E402
import revenue_mvp_reduced_surface_gate_mapping as mapping  # noqa: E402


class ReducedSurfaceGateMappingTests(unittest.TestCase):
    def test_current_versioned_evidence_is_review_candidate_only(self):
        result = mapping.review_reduced_surface_gate_mapping(
            mapping.current_versioned_evidence()
        )
        self.assertEqual(result.status, mapping.REVIEW_CANDIDATE)
        self.assertEqual(result.surface_scope, "REDUCED_SURFACE")
        self.assertEqual(result.publication_readiness_status, "BLOCKED")
        self.assertEqual(result.publication_status, "CLOSED")
        self.assertFalse(result.gate_mutation_allowed)
        self.assertFalse(result.production_allowed)
        self.assertFalse(result.affiliate_allowed)

    def test_required_semantics_are_satisfied_only_for_reduced_review(self):
        result = mapping.review_reduced_surface_gate_mapping(
            mapping.current_versioned_evidence()
        )
        self.assertEqual(
            {row["semantic"] for row in result.required_semantics},
            set(mapping.REQUIRED_SEMANTICS),
        )
        self.assertTrue(all(
            row["status"] == mapping.SATISFIED
            for row in result.required_semantics
        ))

    def test_ordinal_update_and_history_are_out_of_scope_not_resolved(self):
        result = mapping.review_reduced_surface_gate_mapping(
            mapping.current_versioned_evidence()
        )
        self.assertEqual(
            {row["semantic"] for row in result.out_of_scope_semantics},
            set(mapping.OUT_OF_SCOPE_SEMANTICS),
        )
        self.assertTrue(all(
            row["status"] == mapping.OUT_OF_SCOPE
            for row in result.out_of_scope_semantics
        ))
        self.assertNotIn("RESOLVED", json.dumps(result.to_dict()))

    def test_existing_registry_and_full_surfaces_remain_blocked(self):
        result = mapping.review_reduced_surface_gate_mapping(
            mapping.current_versioned_evidence()
        )
        self.assertEqual(
            tuple(row["status"] for row in result.existing_blocker_statuses),
            tuple(blockers.BLOCKERS[key].status for key in blockers.BLOCKER_IDS),
        )
        self.assertEqual(
            result.full_surface_status, blockers.PENDING_OFFICIAL_CONFIRMATION
        )
        self.assertEqual(
            result.expanded_surface_status,
            blockers.PENDING_OFFICIAL_CONFIRMATION,
        )

    def test_missing_unknown_or_version_mismatch_fails_closed(self):
        current = mapping.current_versioned_evidence()
        cases = (
            None,
            {},
            replace(current, mapping_version="unknown"),
            replace(current, launch_rehearsal_version="unknown"),
            replace(current, lifecycle_policy_verified=1),
        )
        for value in cases:
            with self.subTest(value=value):
                result = mapping.review_reduced_surface_gate_mapping(value)
                self.assertEqual(result.status, mapping.FAIL_CLOSED)
                self.assertFalse(result.gate_mutation_allowed)
                self.assertEqual(result.publication_status, "CLOSED")

    def test_any_incomplete_evidence_is_blocked(self):
        current = mapping.current_versioned_evidence()
        fields = (
            "lifecycle_policy_verified",
            "reduced_surface_contract_verified",
            "lifecycle_filter_verified",
            "artifact_integration_verified",
            "launch_rehearsal_verified",
        )
        for field in fields:
            with self.subTest(field=field):
                result = mapping.review_reduced_surface_gate_mapping(
                    replace(current, **{field: False})
                )
                self.assertEqual(result.status, mapping.BLOCKED)
                self.assertFalse(result.production_allowed)

    def test_existing_gate_drift_fails_closed_without_mutation(self):
        with mock.patch.object(mapping.blockers, "validate_registry", return_value=("DRIFT",)):
            result = mapping.review_reduced_surface_gate_mapping(
                mapping.current_versioned_evidence()
            )
        self.assertEqual(result.status, mapping.FAIL_CLOSED)
        self.assertIn("EXISTING_GATE_BOUNDARY_CHANGED", result.reason_codes)

    def test_output_is_bounded_and_source_has_no_external_io(self):
        result = mapping.review_reduced_surface_gate_mapping(
            mapping.current_versioned_evidence()
        )
        text = json.dumps(result.to_dict()).lower()
        for forbidden in ("api_id", "affiliate_id", "content_id", "credential"):
            self.assertNotIn(forbidden, text)
        source = Path(mapping.__file__).read_text(encoding="utf-8")
        for forbidden in (
            "open(", "read_text(", "write_text(", "sqlite3", "requests",
            "urllib", "subprocess", "fetch(", "deploy(", "scheduler",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
