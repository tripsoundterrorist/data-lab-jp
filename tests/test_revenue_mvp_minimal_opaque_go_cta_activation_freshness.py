from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_minimal_opaque_go_cta_activation_freshness as subject  # noqa: E402
import revenue_mvp_minimal_opaque_go_cta_activation_review as activation  # noqa: E402


STAMP = "2026-09-25T07:00:06Z"
NOW = datetime(2026, 9, 25, 8, 0, tzinfo=timezone.utc)
PUBLIC_ID = "itm_0123456789abcdef01234567"


def artifact(stamp=STAMP) -> bytes:
    return (
        '<!doctype html><html><head><meta name="robots" content="noindex,nofollow"></head>'
        '<body><main><article><time datetime="' + stamp + '">' + stamp + '</time>'
        '<aside class="affiliate-cta-block">'
        '<p class="affiliate-cta-disclosure">【PR】FANZAで確認</p>'
        f'<a class="affiliate-cta-link" href="/go/{PUBLIC_ID}" target="_blank" '
        'rel="noopener noreferrer sponsored">確認</a>'
        '</aside></article></main></body></html>\n'
    ).encode("utf-8")


class MinimalOpaqueGoCtaActivationFreshnessTests(unittest.TestCase):
    def patched_review(self, value: bytes, now=NOW):
        digest = hashlib.sha256(value).hexdigest()
        with mock.patch.object(activation, "COMPLIANCE_APPROVED_ARTIFACT_SHA256", digest):
            return subject.review(value, evaluated_at=now)

    def test_exact_fresh_artifact_is_review_ready_not_active(self):
        result = self.patched_review(artifact())
        self.assertEqual(result.status, subject.FRESH)
        self.assertTrue(result.freshness_confirmed)
        self.assertTrue(result.ready_to_request_explicit_activation_review)
        self.assertTrue(all(not getattr(result, field) for field in (
            "publication_allowed", "production_activation_allowed",
            "affiliate_eligibility_allowed", "gate_mutation_allowed",
            "d1_write_allowed", "deployment_allowed",
        )))

    def test_stale_future_or_invalid_time_fails_closed(self):
        for now in (
            NOW + timedelta(hours=25),
            datetime(2026, 9, 25, 7, 0, 5, tzinfo=timezone.utc),
        ):
            with self.subTest(now=now):
                self.assertEqual(self.patched_review(artifact(), now).status, subject.BLOCKED)
        self.assertEqual(self.patched_review(artifact("invalid")).status, subject.BLOCKED)

    def test_wrong_artifact_or_duplicate_time_fails_closed(self):
        self.assertEqual(subject.review(artifact(), evaluated_at=NOW).status, subject.BLOCKED)
        value = artifact().replace(b"</article>", f'<time datetime="{STAMP}">{STAMP}</time></article>'.encode())
        self.assertEqual(self.patched_review(value).status, subject.BLOCKED)

    def test_invalid_evaluation_time_fails_closed(self):
        value = artifact()
        digest = hashlib.sha256(value).hexdigest()
        with mock.patch.object(activation, "COMPLIANCE_APPROVED_ARTIFACT_SHA256", digest):
            self.assertEqual(subject.review(value, evaluated_at=None).status, subject.BLOCKED)
            self.assertEqual(
                subject.review(value, evaluated_at=datetime(2026, 9, 25, 8, 0)).status,
                subject.BLOCKED,
            )


if __name__ == "__main__":
    unittest.main()
