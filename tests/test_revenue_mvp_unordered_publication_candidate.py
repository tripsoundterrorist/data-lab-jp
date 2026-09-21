from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_unordered_publication_candidate as candidate  # noqa: E402
import revenue_mvp_unordered_surface_review as contract  # noqa: E402

NOW = datetime(2026, 9, 22, 10, 0, tzinfo=timezone.utc)
STAMP = "2026-09-22T09:30:00Z"


def packet():
    return {
        "version": "0.1-candidate", "mode": "UNORDERED_GRID", "as_of": STAMP,
        "transparency_notice": contract.TRANSPARENCY_NOTICE,
        "candidates": [{"title": "架空の検証用商品", "api_observed_at": STAMP,
                        "transparency_notice": contract.TRANSPARENCY_NOTICE,
                        "current_price": 1200, "price_observed_at": STAMP}],
        "publication_allowed": False, "production_activation_allowed": False,
        "affiliate_eligibility_allowed": False, "gate_mutation_allowed": False,
        "cta_allowed": False,
    }


class CandidateTests(unittest.TestCase):
    def render(self, value=None):
        raw = json.dumps(value or packet(), ensure_ascii=False, sort_keys=True).encode()
        return candidate.render(raw, evaluated_at=NOW, target_route="/items/")

    def test_deterministic_and_receipt_binds_packet_artifact_and_route(self):
        first, receipt = self.render()
        second, again = self.render()
        self.assertEqual(first, second)
        self.assertEqual(receipt, again)
        self.assertEqual(receipt.artifact_sha256, hashlib.sha256(first).hexdigest())
        self.assertEqual(receipt.target_route, "/items/")
        self.assertFalse(receipt.publication_allowed)
        self.assertIn(b"noindex,nofollow", first)

    def test_html_is_escaped_and_contains_no_link_or_identifier(self):
        value = packet(); value["candidates"][0]["title"] = '<script>alert(1)</script>'
        rendered, _ = self.render(value)
        self.assertNotIn(b"<script>", rendered)
        self.assertNotIn(b"https://example", rendered)
        self.assertNotIn(b"items.js", rendered)

    def test_fail_closed_for_extra_field_activation_stale_or_price_mismatch(self):
        mutations = []
        value = packet(); value["candidates"][0]["content_id"] = "x"; mutations.append(value)
        value = packet(); value["publication_allowed"] = True; mutations.append(value)
        value = packet(); value["as_of"] = "2026-09-20T00:00:00Z"; mutations.append(value)
        value = packet(); value["candidates"][0]["price_observed_at"] = "2026-09-22T09:29:00Z"; mutations.append(value)
        for value in mutations:
            with self.subTest(value=value), self.assertRaises(candidate.CandidateFailure):
                self.render(value)

    def test_output_inside_repository_is_rejected(self):
        with self.assertRaises(candidate.CandidateFailure):
            candidate.write_candidate(ROOT / "candidate.html", b"x")
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "candidate.html"
            candidate.write_candidate(target, b"ok")
            self.assertEqual(target.read_bytes(), b"ok")


if __name__ == "__main__":
    unittest.main()
