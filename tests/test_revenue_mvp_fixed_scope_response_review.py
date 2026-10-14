from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import revenue_mvp_fixed_scope_response_review as subject
import revenue_mvp_fixed_scope_acquisition_plan as planner
import revenue_mvp_fixed_scope_refresh_review as reviewer
from hashlib import sha256
from revenue_mvp_lifecycle_receipt import public_item_id

STAMP = datetime(2026, 10, 14, tzinfo=timezone.utc)
CID = "fixture-001"
PUBLIC = public_item_id("FANZA", "digital", "videoa", CID)


def fixture():
    return {"result": {"status": 200, "result_count": 1, "total_count": 1,
            "items": [{"content_id": CID, "service_code": "digital",
                       "floor_code": "videoa",
                       "affiliateURL": "https://al.fanza.co.jp/?fixture=1",
                       "prices": {"price": "1000~"},
                       "imageURL": {"large": "https://pics.dmm.co.jp/fixture.jpg"}}]}}


class FixedResponseTests(unittest.TestCase):
    def decode(self, payload=None, **options):
        values = dict(target_public_id=PUBLIC, resolved_content_id=CID,
                      payload=fixture() if payload is None else payload,
                      http_status=200, observed_at=STAMP, evaluated_at=STAMP)
        values.update(options)
        return subject.decode(**values)

    def test_valid_keeps_lower_bound_and_never_grants_trust_or_execution(self):
        result = self.decode()
        self.assertEqual(result.status, "STRUCTURAL_OBSERVATION_READY")
        self.assertTrue(result.price_is_lower_bound)
        self.assertEqual(result.observation.price, 1000)
        self.assertFalse(result.trusted_acquisition_confirmed)
        self.assertFalse(result.database_write_performed)
        self.assertFalse(result.publication_allowed)
        self.assertEqual(result.api_calls, 0)
        self.assertNotIn("https://", str(result.summary()))
        self.assertNotIn(CID, repr(result))
        self.assertNotIn(PUBLIC, repr(result))

    def test_identity_hash_binding_and_returned_id(self):
        self.assertEqual(self.decode(resolved_content_id="other").status, "BLOCKED")
        data = fixture()
        data["result"]["items"][0]["content_id"] = "other"
        self.assertEqual(self.decode(data).reason_code, "EXACT_ITEM_MISMATCH")

    def test_zero_not_sales_end(self):
        data = {"result": {"status": 200, "result_count": 0, "total_count": 0, "items": []}}
        self.assertEqual(self.decode(data).reason_code, "NO_MATCH_REQUIRES_SEPARATE_REVIEW")

    def test_duplicate_or_inconsistent_counts_rejected(self):
        for field, value in (("result_count", 0), ("result_count", True),
                             ("total_count", 2), ("total_count", -1)):
            data = fixture()
            data["result"][field] = value
            self.assertEqual(self.decode(data).status, "BLOCKED")
        data = fixture()
        data["result"]["items"].append(deepcopy(data["result"]["items"][0]))
        data["result"]["result_count"] = 2
        data["result"]["total_count"] = 2
        self.assertEqual(self.decode(data).status, "BLOCKED")

    def test_rate_limit_stops(self):
        self.assertEqual(self.decode(http_status=429).reason_code, "STOP_RATE_LIMIT")
        data = fixture()
        data["result"]["status"] = 429
        self.assertEqual(self.decode(data).reason_code, "STOP_RATE_LIMIT")

    def test_missing_price_image_affiliate_and_scope_rejected(self):
        for field in ("prices", "imageURL", "affiliateURL", "service_code", "floor_code"):
            data = fixture()
            del data["result"]["items"][0][field]
            self.assertEqual(self.decode(data).status, "BLOCKED")

    def test_bad_price_unsafe_urls_and_boolean_status_rejected(self):
        for price in (None, True, "unknown", "-1", "100-200", "100~200"):
            data = fixture()
            data["result"]["items"][0]["prices"]["price"] = price
            self.assertEqual(self.decode(data).status, "BLOCKED")
        data = fixture()
        data["result"]["items"][0]["imageURL"]["large"] = "https://other.invalid/x"
        self.assertEqual(self.decode(data).status, "BLOCKED")
        data = fixture()
        data["result"]["items"][0]["affiliateURL"] = "https://other.invalid/x"
        self.assertEqual(self.decode(data).status, "BLOCKED")
        self.assertEqual(self.decode(http_status=True).status, "BLOCKED")

    def test_exact_price_is_distinct_from_lower_bound(self):
        data = fixture()
        data["result"]["items"][0]["prices"]["price"] = "0"
        result = self.decode(data)
        self.assertEqual(result.observation.price, 0)
        self.assertFalse(result.price_is_lower_bound)

    def test_future_stale_and_naive_times_rejected(self):
        for stamp in (STAMP + timedelta(seconds=1), STAMP - timedelta(hours=25),
                      STAMP.replace(tzinfo=None)):
            self.assertEqual(self.decode(observed_at=stamp).status, "BLOCKED")

    def test_mock_100_item_plan_decode_and_review(self):
        identities = {public_item_id("FANZA", "digital", "videoa", f"fixture-{i:03}"):
                      f"fixture-{i:03}" for i in range(100)}
        old = (STAMP - timedelta(days=1)).isoformat()
        markup = "".join(f'<article class="item"><time>{old}</time>'
                         f'<a href="/go/{value}">fixture</a></article>'
                         for value in identities).encode()
        digest = sha256(markup).hexdigest()
        plan = planner.build(markup, digest)
        observations = []
        for batch in plan.batches:
            for value in batch:
                payload = fixture()
                payload["result"]["items"][0]["content_id"] = identities[value]
                decoded = subject.decode(target_public_id=value,
                    resolved_content_id=identities[value], payload=payload,
                    http_status=200, observed_at=STAMP, evaluated_at=STAMP)
                self.assertEqual(decoded.status, "STRUCTURAL_OBSERVATION_READY")
                observations.append(decoded.observation)
        result = reviewer.review(markup, digest, tuple(observations), evaluated_at=STAMP)
        self.assertEqual(result.status, "STRUCTURAL_REVIEW_READY")
        self.assertFalse(plan.execution_allowed)
        self.assertFalse(result.publication_allowed)
        self.assertEqual(plan.api_calls, 0)
        # A decoder failure must not be filled with old data or another item.
        incomplete = reviewer.review(markup, digest, tuple(observations[:-1]),
                                     evaluated_at=STAMP)
        self.assertEqual(incomplete.reason_code, "OBSERVATION_COVERAGE_INVALID")

    def test_malformed_payload_rejected(self):
        for payload in ({}, {"result": None}, {"result": {"status": "200"}}, []):
            self.assertEqual(self.decode(payload).status, "BLOCKED")


if __name__ == "__main__":
    unittest.main()
