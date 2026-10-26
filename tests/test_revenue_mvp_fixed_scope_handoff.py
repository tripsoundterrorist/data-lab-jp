"""Synthetic-only boundary tests for the isolated prototype."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import unittest

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import revenue_mvp_fixed_scope_handoff as handoff
from revenue_mvp_fixed_scope_refresh_review import Observation
from revenue_mvp_fixed_scope_response_review import DecodeResult


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 26, 12, tzinfo=timezone.utc)
        self.source = ("<main>" + "".join(
            f'<article class="item"><time>2026-09-30T00:00:00Z</time><a href="/go/itm_{i:024x}">test</a></article>'
            for i in range(100)) + "</main>").encode()
        self.digest = sha256(self.source).hexdigest()
        stamp = self.now - timedelta(minutes=1)
        self.rows = tuple(DecodeResult("STRUCTURAL_OBSERVATION_READY", "TEST",
            Observation(f"itm_{i:024x}", stamp, 100, "https://pics.dmm.co.jp/test.jpg",
                        stamp, stamp, stamp, "VALID"), bool(i % 2)) for i in range(5))

    def call(self, rows=None, **kwargs):
        args = dict(batch_index=0, evaluated_at=self.now)
        args.update(kwargs)
        return handoff.build(self.source, self.digest, "a" * 64,
                            self.rows if rows is None else rows, **args)

    def blocked(self, rows=None, **kwargs):
        receipt, payload = self.call(rows, **kwargs)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIsNone(payload)
        self.assertFalse(receipt["publication_allowed"])

    def test_preserves_lower_bound_and_sanitizes(self):
        receipt, payload = self.call()
        self.assertEqual(receipt["record_count"], 5)
        value = json.loads(payload)
        self.assertEqual([r["price_is_lower_bound"] for r in value["records"]], [False, True, False, True, False])
        self.assertFalse(value["trusted_acquisition_confirmed"])
        self.assertEqual(set(value["records"][0]), {"public_id", "price", "price_is_lower_bound", "image_url", "observed_at"})
        for forbidden in (b"affiliateURL", b"api_id", b"token", b"raw_payload"):
            self.assertNotIn(forbidden, payload)

    def test_partial_duplicate_wrong_scope(self):
        for rows in (self.rows[:4], self.rows + self.rows[:1],
                     self.rows[:4] + self.rows[:1]):
            with self.subTest(rows=len(rows)):
                self.blocked(rows)
        self.blocked(batch_index=1)

    def test_bad_field_variants(self):
        original = self.rows[0]
        for change in ({"price": True}, {"price": -1}, {"price": 10**12},
                       {"image_url": None}, {"image_url": "https://evil.test/x"},
                       {"image_url": "https://pics.dmm.co.jp/x?key=secret"},
                       {"image_observed_at": self.now}, {"outcome": "NOT_AVAILABLE"}):
            with self.subTest(change=change):
                row = replace(original, observation=replace(original.observation, **change))
                self.blocked((row,) + self.rows[1:])

    def test_stale_future_naive_times(self):
        for when in (self.now-timedelta(hours=25), self.now+timedelta(seconds=1), self.now.replace(tzinfo=None)):
            row = self.rows[0]
            obs = replace(row.observation, observed_at=when, price_observed_at=when,
                          image_observed_at=when, lifecycle_observed_at=when)
            self.blocked((replace(row, observation=obs),) + self.rows[1:])

    def test_flags_types_and_binding(self):
        for value in (None, 0, 1, "true"):
            self.blocked((replace(self.rows[0], price_is_lower_bound=value),) + self.rows[1:])
        self.blocked(batch_index=True)
        self.blocked(evaluated_at=self.now.replace(tzinfo=None))
        receipt, data = handoff.build(self.source, "0" * 64, "a" * 64,
            self.rows, batch_index=0, evaluated_at=self.now)
        self.assertIsNone(data)
        self.assertEqual(receipt["reason_code"], "INPUT_BINDING_INVALID")

    def test_deterministic_and_non_authorizing(self):
        receipt, data = self.call()
        other, reversed_data = self.call(tuple(reversed(self.rows)))
        self.assertEqual(data, reversed_data)
        self.assertEqual(receipt["payload_sha256"], sha256(data).hexdigest())
        for field in ("output_written", "database_write_performed", "publication_allowed", "trusted_acquisition_confirmed"):
            self.assertFalse(receipt[field])
        self.assertEqual(receipt["api_calls"], 0)

    def test_requires_strictly_newer_observation_than_published(self):
        original = self.source
        for published in ("2026-10-26T11:59:00Z", "2026-10-26T11:59:30Z"):
            with self.subTest(published=published):
                self.source = original.replace(b"2026-09-30T00:00:00Z", published.encode())
                self.digest = sha256(self.source).hexdigest()
                receipt, payload = self.call()
                self.assertIsNone(payload)
                self.assertEqual(receipt["reason_code"], "OBSERVATION_NOT_NEWER_THAN_PUBLISHED")

    def test_timezone_equivalence_and_freshness_boundary(self):
        local = timezone(timedelta(hours=9))
        rows = tuple(replace(row, observation=replace(row.observation,
            image_observed_at=row.observation.image_observed_at.astimezone(local))) for row in self.rows)
        self.assertEqual(self.call(rows)[0]["record_count"], 5)
        stamp = self.now - timedelta(hours=24)
        boundary = tuple(replace(row, observation=replace(row.observation,
            observed_at=stamp, price_observed_at=stamp, image_observed_at=stamp,
            lifecycle_observed_at=stamp)) for row in self.rows)
        self.assertEqual(self.call(boundary)[0]["record_count"], 5)
        self.blocked(boundary, evaluated_at=self.now + timedelta(microseconds=1))


if __name__ == "__main__":
    unittest.main()
