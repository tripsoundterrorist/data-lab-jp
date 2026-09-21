from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_rendered_artifact_preflight as preflight  # noqa: E402
import revenue_mvp_unordered_publication_candidate as renderer  # noqa: E402
import revenue_mvp_unordered_surface_review as contract  # noqa: E402

STAMP = "2026-09-22T09:30:00Z"


def packet():
    return {
        "version": "0.1-candidate", "mode": "UNORDERED_GRID", "as_of": STAMP,
        "transparency_notice": contract.TRANSPARENCY_NOTICE,
        "candidates": [{"title": "架空の検証用商品", "api_observed_at": STAMP,
                        "transparency_notice": contract.TRANSPARENCY_NOTICE}],
        "publication_allowed": False, "production_activation_allowed": False,
        "affiliate_eligibility_allowed": False, "gate_mutation_allowed": False,
        "cta_allowed": False,
    }


class RenderedArtifactPreflightTests(unittest.TestCase):
    def artifact(self):
        raw = json.dumps(packet(), ensure_ascii=False, sort_keys=True).encode()
        return renderer.render(raw, evaluated_at=datetime(2026, 9, 22, 10, tzinfo=timezone.utc), target_route="/items/")[0]

    def test_pass_receipt_remains_non_activating_and_records_rollback(self):
        html = self.artifact(); digest = hashlib.sha256(html).hexdigest()
        result = preflight.validate_and_preflight(html, expected_sha256=digest,
            expected_count=1, target_route="/items/", repo_root=ROOT)
        self.assertEqual(result.status, "READY_FOR_EXPLICIT_ACTIVATION_REVIEW")
        self.assertEqual(result.rendered_artifact_validation, "PASS")
        self.assertEqual(result.route_configuration_review, "EXISTING_STATIC_ROUTE_CONFIRMED")
        self.assertTrue(result.explicit_user_approval_required)
        self.assertFalse(result.public_data_deployment_allowed)
        self.assertIn("CLOSED", result.rollback_action)

    def test_hash_count_route_and_existing_source_fail_closed(self):
        html = self.artifact(); digest = hashlib.sha256(html).hexdigest()
        cases = [
            {"expected_sha256": "0" * 64, "expected_count": 1, "target_route": "/items/", "repo_root": ROOT},
            {"expected_sha256": digest, "expected_count": 2, "target_route": "/items/", "repo_root": ROOT},
            {"expected_sha256": digest, "expected_count": 1, "target_route": "/other/", "repo_root": ROOT},
            {"expected_sha256": digest, "expected_count": 1, "target_route": "/items/", "repo_root": ROOT / "missing"},
        ]
        for values in cases:
            with self.subTest(values=values), self.assertRaises(preflight.ValidationFailure):
                preflight.validate_and_preflight(html, **values)

    def test_active_or_external_markup_is_rejected(self):
        html = self.artifact(); tampered = html.replace(b'<main id="main-content">', b'<main id="main-content"><a href="https://example.com">x</a>')
        with self.assertRaises(preflight.ValidationFailure):
            preflight.validate_and_preflight(tampered,
                expected_sha256=hashlib.sha256(tampered).hexdigest(), expected_count=1,
                target_route="/items/", repo_root=ROOT)


if __name__ == "__main__":
    unittest.main()
