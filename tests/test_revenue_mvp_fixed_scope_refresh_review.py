from dataclasses import replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import revenue_mvp_fixed_scope_refresh_review as subject

OLD = datetime(2026, 10, 1, tzinfo=timezone.utc)
NEW = OLD + timedelta(days=1)
NOW = NEW + timedelta(hours=1)


def identity(i):
    return f"itm_{i:024x}"


def source(ids=range(100)):
    return "".join(f'<article class="item"><time>{OLD.isoformat()}</time>'
                   f'<a href="/go/{identity(i)}">fixture</a></article>'
                   for i in ids).encode()


def rows():
    return tuple(subject.Observation(identity(i), NEW, 1000,
                 "https://pics.dmm.co.jp/fixture.jpg", NEW, NEW, NEW, "VALID")
                 for i in range(100))


class FixedScopeRefreshTests(unittest.TestCase):
    def review(self, values=None, markup=None, digest=None):
        markup = source() if markup is None else markup
        return subject.review(markup, digest or sha256(markup).hexdigest(),
                              rows() if values is None else values, evaluated_at=NOW)

    def changed(self, **changes):
        values = rows()
        return self.review((replace(values[0], **changes),) + values[1:])

    def test_ready_is_never_publication_permission(self):
        result = self.review()
        self.assertEqual(result.status, "STRUCTURAL_REVIEW_READY")
        for flag in ("publication_allowed", "api_request_performed",
                     "database_write_performed", "production_write_performed"):
            self.assertFalse(getattr(result, flag))

    def test_99_rotated_items_rejected(self):
        rotated = (rows()[0],) + tuple(replace(r, public_id=identity(i + 100))
                                      for i, r in enumerate(rows()[1:]))
        self.assertEqual(self.review(rotated).reason_code, "SCOPE_CHANGED_OR_DUPLICATED")

    def test_missing_observation_rejected(self):
        self.assertEqual(self.review(rows()[:-1]).status, "BLOCKED")

    def test_duplicate_observation_rejected(self):
        self.assertEqual(self.review((rows()[1],) + rows()[1:]).status, "BLOCKED")

    def test_duplicate_source_rejected(self):
        self.assertEqual(self.review(markup=source([0] * 100)).status, "BLOCKED")

    def test_source_hash_mismatch_rejected(self):
        self.assertEqual(self.review(digest="0" * 64).reason_code, "SOURCE_BINDING_INVALID")

    def test_stale_future_and_unchanged_observations_rejected(self):
        for stamp in (OLD, NOW + timedelta(seconds=1), NOW - timedelta(hours=25)):
            with self.subTest(stamp=stamp):
                self.assertEqual(self.changed(observed_at=stamp).status, "BLOCKED")

    def test_old_image_or_price_provenance_rejected(self):
        for field in ("image_observed_at", "price_observed_at", "lifecycle_observed_at"):
            with self.subTest(field=field):
                self.assertEqual(self.changed(**{field: OLD}).reason_code,
                                 "FIELD_PROVENANCE_MISMATCH")

    def test_unknown_outcome_rejected(self):
        self.assertEqual(self.changed(outcome="UNCONFIRMED").reason_code,
                         "OBSERVATION_UNCONFIRMED")

    def test_unavailable_requires_separate_review(self):
        self.assertEqual(self.changed(outcome="NOT_AVAILABLE").reason_code,
                         "SEPARATE_TAKEDOWN_REVIEW_REQUIRED")

    def test_missing_unsafe_image_and_invalid_price_rejected(self):
        for changes in ({"image_url": None}, {"image_url": "https://other.invalid/x"},
                        {"image_url": "https://pics.dmm.co.jp@other.invalid/x"},
                        {"price": None}, {"price": True}, {"price": -1}):
            with self.subTest(changes=changes):
                self.assertEqual(self.changed(**changes).status, "BLOCKED")

    def test_naive_timestamp_rejected(self):
        self.assertEqual(self.changed(observed_at=NEW.replace(tzinfo=None)).status, "BLOCKED")

    def test_missing_source_time_or_route_rejected(self):
        for markup in (source().replace(b"<time>", b"<span>").replace(b"</time>", b"</span>"),
                       source().replace(b"/go/", b"/other/")):
            self.assertEqual(self.review(markup=markup).status, "BLOCKED")


if __name__ == "__main__":
    unittest.main()
