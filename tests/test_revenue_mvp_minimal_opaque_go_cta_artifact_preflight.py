import hashlib
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_minimal_opaque_go_cta_artifact_preflight as subject  # noqa: E402


PUBLIC_ID = "itm_0123456789abcdef01234567"


def artifact(*, disclosure="【PR】FANZAで確認", href=f"/go/{PUBLIC_ID}", extra="") -> bytes:
    return (
        '<!doctype html><html><head><meta name="robots" content="noindex,nofollow"></head>'
        '<body><main><article><aside class="affiliate-cta-block">'
        f'<p class="affiliate-cta-disclosure">{disclosure}</p>{extra}'
        f'<a class="affiliate-cta-link" href="{href}" target="_blank" '
        'rel="noopener noreferrer sponsored">確認</a>'
        '</aside></article></main></body></html>\n'
    ).encode("utf-8")


def review(value: bytes):
    return subject.review(value, hashlib.sha256(value).hexdigest())


class MinimalOpaqueGoCtaArtifactPreflightTests(unittest.TestCase):
    def test_exact_safe_structure_is_manual_review_only(self):
        value = artifact()
        result = review(value)
        self.assertEqual(result.status, subject.PASS)
        self.assertTrue(result.eligible_for_manual_activation_review)
        self.assertTrue(result.noindex_confirmed)
        self.assertTrue(result.same_origin_confirmed)
        self.assertTrue(result.proximate_disclosure_confirmed)
        self.assertTrue(all(not getattr(result, field) for field in (
            "publication_allowed", "production_activation_allowed",
            "affiliate_eligibility_allowed", "gate_mutation_allowed",
            "deployment_allowed",
        )))

    def test_digest_private_value_and_dangerous_element_fail_closed(self):
        value = artifact()
        self.assertEqual(subject.review(value, "0" * 64).status, subject.BLOCKED)
        self.assertEqual(review(value.replace(b"</body>", b"affiliateURL</body>")).status, subject.BLOCKED)
        self.assertEqual(review(value.replace(b"</body>", b"<script></script></body>")).status, subject.BLOCKED)

    def test_external_or_unsafe_link_fails_closed(self):
        self.assertEqual(review(artifact(href="https://example.invalid")).status, subject.BLOCKED)
        value = artifact().replace(b" sponsored", b"")
        self.assertEqual(review(value).status, subject.BLOCKED)

    def test_disclosure_text_and_proximity_fail_closed(self):
        self.assertEqual(review(artifact(disclosure="FANZAで確認")).status, subject.BLOCKED)
        self.assertEqual(review(artifact(extra="<span>separate</span>")).status, subject.BLOCKED)

    def test_duplicate_or_missing_units_fail_closed(self):
        value = artifact()
        duplicate = value.replace(b"</article>", value[value.index(b"<aside"):value.index(b"</aside>") + 8] + b"</article>")
        self.assertEqual(review(duplicate).status, subject.BLOCKED)
        self.assertEqual(review(value.replace(b"affiliate-cta-link", b"other-link")).status, subject.BLOCKED)
        outside = value.replace(
            b"</main>", f'<a href="/go/{PUBLIC_ID}">extra</a></main>'.encode(),
        )
        self.assertEqual(review(outside).status, subject.BLOCKED)


if __name__ == "__main__":
    unittest.main()
