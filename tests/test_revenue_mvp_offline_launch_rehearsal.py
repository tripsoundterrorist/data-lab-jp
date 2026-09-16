from dataclasses import replace
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from tests.test_revenue_mvp_offline_artifact_integration import (  # noqa: E402
    PUBLIC_ID, encoded, evidence, fixture,
)
import revenue_mvp_offline_launch_rehearsal as rehearsal  # noqa: E402


def excluded_scenarios():
    excluded = evidence(False)
    return tuple(
        rehearsal.ExclusionScenario(name, {PUBLIC_ID: excluded})
        for name in sorted(rehearsal.REQUIRED_EXCLUSION_SCENARIOS)
    )


def forbidden_scenarios():
    scenarios = []
    for field in ("first_position", "source_position", "offset", "rank", "top", "latest"):
        files = fixture()
        documents = {path: json.loads(content) for path, content in files.items()}
        documents["index.json"]["items"][0][field] = 1
        files["index.json"] = encoded(documents["index.json"])
        scenarios.append(rehearsal.ForbiddenScenario(field, files))
    return tuple(scenarios)


class OfflineLaunchRehearsalTests(unittest.TestCase):
    def test_complete_offline_rehearsal(self):
        result = rehearsal.run_offline_launch_rehearsal(
            fixture(), {PUBLIC_ID: evidence()}, excluded_scenarios(),
            forbidden_scenarios(),
        )
        self.assertEqual(result.status, rehearsal.REHEARSAL_COMPLETE)
        self.assertTrue(result.candidate_index_detail_consistent)
        self.assertTrue(result.candidate_cta_disabled)
        self.assertEqual(result.exclusions_verified, result.exclusions_required)
        self.assertTrue(result.manifest_count_digest_verified)
        self.assertTrue(result.forbidden_inputs_fail_closed)
        self.assertTrue(result.rollback_deterministic)
        self.assertIsNotNone(result.rollback_source_sha256)
        self.assertFalse(result.production_publication_allowed)
        self.assertFalse(result.publication_gate_change_allowed)
        self.assertFalse(result.external_io_performed)

    def test_rollback_is_byte_exact_and_does_not_alias_source(self):
        source = fixture()
        restored = rehearsal.restore_local_validation_snapshot(source)
        self.assertEqual(restored, source)
        self.assertIsNot(restored, source)
        restored["index.json"] = b"changed"
        self.assertNotEqual(restored, source)

    def test_invalid_or_nonlocal_snapshot_cannot_be_restored(self):
        files = fixture()
        manifest = json.loads(files["manifest.json"])
        manifest["publication_status"] = "public"
        files["manifest.json"] = encoded(manifest)
        self.assertEqual(rehearsal.restore_local_validation_snapshot(files), {})
        self.assertEqual(rehearsal.restore_local_validation_snapshot(None), {})

    def test_missing_exclusion_or_forbidden_scenario_fails_closed(self):
        cases = (
            (excluded_scenarios()[:-1], forbidden_scenarios()),
            (excluded_scenarios(), ()),
        )
        for exclusions, forbidden in cases:
            with self.subTest(exclusions=len(exclusions), forbidden=len(forbidden)):
                result = rehearsal.run_offline_launch_rehearsal(
                    fixture(), {PUBLIC_ID: evidence()}, exclusions, forbidden
                )
                self.assertEqual(result.status, rehearsal.FAIL_CLOSED)
                self.assertFalse(result.production_publication_allowed)

    def test_tampered_candidate_evidence_fails_closed(self):
        item = evidence()
        unsafe = replace(
            item.lifecycle, publication_allowed=True,
        )
        result = rehearsal.run_offline_launch_rehearsal(
            fixture(), {PUBLIC_ID: replace(item, lifecycle=unsafe)},
            excluded_scenarios(), forbidden_scenarios(),
        )
        self.assertEqual(result.status, rehearsal.FAIL_CLOSED)

    def test_source_has_no_external_or_filesystem_io(self):
        source = Path(rehearsal.__file__).read_text(encoding="utf-8")
        for forbidden in (
            "open(", "read_text(", "write_text(", "sqlite3", "requests",
            "urllib", "subprocess", "fetch(", "scheduler", "deploy",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
