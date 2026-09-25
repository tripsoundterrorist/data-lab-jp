from datetime import datetime, timezone
import hashlib
from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_minimal_opaque_go_cta_activation_review as activation  # noqa: E402
import revenue_mvp_minimal_opaque_go_cta_live_integration as subject  # noqa: E402


NOW = datetime(2026, 9, 25, 8, 0, tzinfo=timezone.utc)
STAMP = "2026-09-25T07:00:06Z"
PUBLIC_ID = "itm_0123456789abcdef01234567"


def approved_artifact() -> bytes:
    return (
        '<!doctype html><html><head><meta name="robots" content="noindex,nofollow"></head>'
        '<body><main><article><h1>対象商品</h1><time datetime="' + STAMP + '">' + STAMP + '</time>'
        '<aside class="affiliate-cta-block" aria-label="広告リンク">'
        '<p class="affiliate-cta-disclosure">【PR】FANZAで確認</p>'
        f'<a class="affiliate-cta-link" href="/go/{PUBLIC_ID}" target="_blank" '
        'rel="noopener noreferrer sponsored">確認</a>'
        '</aside></article></main></body></html>\n'
    ).encode()


def source(title="対象商品") -> bytes:
    return (
        '<main><section class="item-grid">'
        f'<article class="item"><h2>{title}</h2><p class="price">100円</p></article>'
        '<article class="item"><h2>別商品</h2></article>'
        '</section></main>\n'
    ).encode()


class MinimalOpaqueGoCtaLiveIntegrationTests(unittest.TestCase):
    def build(self, live=None, artifact=None):
        artifact = artifact or approved_artifact()
        digest = hashlib.sha256(artifact).hexdigest()
        with mock.patch.object(activation, "COMPLIANCE_APPROVED_ARTIFACT_SHA256", digest):
            return subject.build_candidate(live or source(), artifact, evaluated_at=NOW)

    def test_one_matching_card_gets_only_exact_cta_diff(self):
        candidate, receipt = self.build()
        result = subject.preflight(
            source(), candidate,
            expected_candidate_sha256=hashlib.sha256(candidate).hexdigest(),
            expected_item_count=2,
        )
        self.assertEqual(receipt.status, subject.READY)
        self.assertEqual(result.status, subject.PASS)
        self.assertEqual(result.item_count, 2)
        self.assertEqual(result.cta_count, 1)
        self.assertTrue(result.source_preserved_except_exact_cta)
        self.assertTrue(all(not getattr(result, field) for field in (
            "publication_allowed", "production_activation_allowed",
            "affiliate_eligibility_allowed", "gate_mutation_allowed",
            "d1_write_allowed", "deployment_allowed", "output_written",
        )))

    def test_missing_duplicate_or_existing_cta_fails_closed(self):
        with self.assertRaises(subject.LiveIntegrationFailure):
            self.build(live=source("missing"))
        with self.assertRaises(subject.LiveIntegrationFailure):
            self.build(live=source() + source())
        with self.assertRaises(subject.LiveIntegrationFailure):
            self.build(live=source().replace(b"</main>", b'<a href="/go/x">x</a></main>'))

    def test_preflight_rejects_any_other_change_or_bad_hash(self):
        candidate, _ = self.build()
        digest = hashlib.sha256(candidate).hexdigest()
        changed = candidate.replace(b"100", b"200")
        self.assertEqual(
            subject.preflight(source(), changed, expected_candidate_sha256=hashlib.sha256(changed).hexdigest(), expected_item_count=2).status,
            subject.BLOCKED,
        )
        self.assertEqual(
            subject.preflight(source(), candidate, expected_candidate_sha256="0" * 64, expected_item_count=2).status,
            subject.BLOCKED,
        )
        self.assertEqual(
            subject.preflight(source(), candidate, expected_candidate_sha256=digest, expected_item_count=True).status,
            subject.BLOCKED,
        )


if __name__ == "__main__":
    unittest.main()
