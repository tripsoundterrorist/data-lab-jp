from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_minimal_opaque_go_cta_renderer as subject  # noqa: E402
import revenue_mvp_unordered_surface_review as unordered  # noqa: E402


STAMP = "2026-09-25T07:00:00Z"
NOW = datetime(2026, 9, 25, 8, 0, tzinfo=timezone.utc)
PUBLIC_ID = "itm_0123456789abcdef01234567"


def packet() -> dict:
    return {
        "version": "0.1-candidate",
        "source_packet_sha256": "a" * 64,
        "as_of": STAMP,
        "selection_method": "OPAQUE_ID_LEXICOGRAPHIC_MIN_NO_RANKING_MEANING",
        "source_candidate_count": 100,
        "candidates": [{
            "title": "<script>検証用タイトル</script>",
            "api_observed_at": STAMP,
            "transparency_notice": unordered.TRANSPARENCY_NOTICE,
            "current_price": 1200,
            "price_observed_at": STAMP,
            "public_id": PUBLIC_ID,
            "cta_href": f"/go/{PUBLIC_ID}",
            "disclosure_text": "【PR】FANZAで確認",
            "disclosure_proximate": True,
        }],
        "publication_allowed": False,
        "production_activation_allowed": False,
        "affiliate_eligibility_allowed": False,
        "gate_mutation_allowed": False,
        "deployment_allowed": False,
    }


def encoded(value: dict | None = None) -> bytes:
    return json.dumps(value or packet(), ensure_ascii=False, sort_keys=True).encode("utf-8")


class MinimalOpaqueGoCtaRendererTests(unittest.TestCase):
    def test_renders_one_inert_proximate_cta_deterministically(self):
        first, receipt = subject.render(encoded(), evaluated_at=NOW)
        second, again = subject.render(encoded(), evaluated_at=NOW)
        self.assertEqual(first, second)
        self.assertEqual(receipt, again)
        text = first.decode("utf-8")
        self.assertIn('content="noindex,nofollow"', text)
        self.assertIn("【PR】FANZAで確認", text)
        self.assertIn(f'href="/go/{PUBLIC_ID}"', text)
        self.assertIn('rel="noopener noreferrer sponsored"', text)
        self.assertNotIn("<script>検証用", text)
        self.assertNotIn("affiliateURL", text)
        self.assertEqual(receipt.artifact_sha256, hashlib.sha256(first).hexdigest())
        self.assertTrue(all(not getattr(receipt, field) for field in (
            "publication_allowed", "production_activation_allowed",
            "affiliate_eligibility_allowed", "gate_mutation_allowed",
            "deployment_allowed", "output_written",
        )))

    def test_activation_schema_route_and_cta_mutations_fail_closed(self):
        mutations = []
        value = packet(); value["publication_allowed"] = True; mutations.append(value)
        value = packet(); value["extra"] = True; mutations.append(value)
        value = packet(); value["candidates"][0]["cta_href"] = "https://example.invalid"; mutations.append(value)
        value = packet(); value["candidates"][0]["disclosure_text"] = "FANZAで確認"; mutations.append(value)
        value = packet(); value["source_candidate_count"] = True; mutations.append(value)
        for value in mutations:
            with self.subTest(value=value), self.assertRaises(subject.CtaRendererFailure):
                subject.render(encoded(value), evaluated_at=NOW)
        with self.assertRaisesRegex(subject.CtaRendererFailure, "TARGET_ROUTE"):
            subject.render(encoded(), evaluated_at=NOW, target_route="/other/")

    def test_stale_or_incomplete_price_fails_closed(self):
        with self.assertRaisesRegex(subject.CtaRendererFailure, "STALE"):
            subject.render(encoded(), evaluated_at=NOW + timedelta(days=2))
        value = packet(); del value["candidates"][0]["price_observed_at"]
        with self.assertRaises(subject.CtaRendererFailure):
            subject.render(encoded(value), evaluated_at=NOW)

    def test_output_must_be_outside_repository(self):
        with self.assertRaises(subject.CtaRendererFailure):
            subject.write_candidate(ROOT / "forbidden.html", b"x")
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "candidate.html"
            subject.write_candidate(target, b"ok")
            self.assertEqual(target.read_bytes(), b"ok")


if __name__ == "__main__":
    unittest.main()
