from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import revenue_mvp_raw_html_review as subject
import revenue_mvp_price_display_transition as transition
import revenue_mvp_price_filter_copy_candidate as copy_candidate


class RawHtmlReviewTests(unittest.TestCase):
    def setUp(self):
        body = (Path(__file__).resolve().parents[1] / "items" / "index.html").read_bytes()
        self.body = transition.canonical(body)
        self.now = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)
        self.args = dict(body=self.body, expected_sha256=transition.CANDIDATE,
                         requested_url=transition.URL, final_url=transition.URL,
                         http_status=200, content_type="text/html; charset=UTF-8",
                         content_encoding="", source_kind="http_response_body",
                         observed_at=self.now, evaluated_at=self.now)

    def review(self, **changes):
        return subject.review(**(self.args | changes))

    def test_match_is_only_supplied_bytes_not_live_authority(self):
        result = self.review()
        self.assertTrue(result.supplied_response_match)
        self.assertEqual(result.status, "SUPPLIED_RESPONSE_MATCH_NOT_TRUSTED_CAPTURE")
        for field in ("trusted_public_capture", "current_eligibility_verified",
                      "publication_allowed", "gate_mutation_allowed"):
            self.assertFalse(getattr(result, field))

    def test_copy_candidate_and_windows_eol(self):
        body, receipt = copy_candidate.build(self.body)
        self.assertTrue(self.review(body=body.replace(b"\n", b"\r\n"),
                                   expected_sha256=receipt.candidate_sha256).supplied_response_match)

    def test_dom_screenshot_and_manual_claims_refused(self):
        for kind in ("dom", "outerHTML", "screenshot", "manual", None):
            with self.subTest(kind=kind):
                self.assertEqual(self.review(source_kind=kind).status, "BLOCKED")

    def test_redirect_status_and_encoding_refused(self):
        for key, values in {
            "requested_url": [transition.URL + "?test=1", "http://datalabx.jp/items/"],
            "final_url": ["https://other.invalid/items/", transition.URL.rstrip("/")],
            "http_status": [403, 302, 201, True, "200"],
            "content_type": [None, "text/plain", "text/html; charset=shift_jis",
                             "text/html; charset=utf-8; charset=utf-8"],
            "content_encoding": [None, "gzip", "br"],
            "expected_sha256": ["0" * 64, transition.BASELINE],
        }.items():
            for value in values:
                with self.subTest(key=key, value=value):
                    self.assertEqual(self.review(**{key: value}).status, "BLOCKED")

    def test_corruption_partial_and_large_body_refused(self):
        for body in (b"", b"\xff", self.body[:-1], self.body + b" ",
                     bytearray(self.body), b"x" * (transition.MAX_BYTES + 1)):
            self.assertEqual(self.review(body=body).status, "BLOCKED")

    def test_time_bounds(self):
        for stamp in (None, self.now.replace(tzinfo=None),
                      self.now + timedelta(seconds=1), self.now - timedelta(minutes=16)):
            self.assertEqual(self.review(observed_at=stamp).status, "BLOCKED")
        self.assertTrue(self.review(observed_at=self.now - timedelta(minutes=15)).supplied_response_match)

    def test_receipt_cannot_enter_existing_trusted_capture_path(self):
        baseline = self.body.replace('円〜</p>'.encode(), '円</p>'.encode())
        result = transition.review(baseline, self.body,
                                   {"items_artifact_sha256": transition.BASELINE},
                                   observation=self.review(), evaluated_at=self.now)
        self.assertEqual(result.reason_code, "TRUSTED_PUBLIC_CAPTURE_REQUIRED")


if __name__ == "__main__":
    unittest.main()
