from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import ebook_comic_projection_candidate as subject  # noqa: E402


def valid_candidate():
    return {
        "projection_version": subject.VERSION,
        "public_id": "ebc_0123456789abcdef01234567",
        "source": {
            "site": "FANZA",
            "service": "ebook",
            "floor": "comic",
            "content_type": "ebook_comic",
            "content_id": "fixture-content",
        },
        "title": "Fixture title",
        "release_date_raw": "2026-01-01",
        "current_price": 100,
        "list_price": None,
        "authors": [{"id": "author-1", "name": "Fixture author"}],
        "manufactures": [{"id": "manufacture-1", "name": "Fixture source"}],
        "series": [{"id": "series-1", "name": "Fixture series"}],
        "genres": [{"id": "genre-1", "name": "Fixture genre"}],
        "image": {
            "large": "https://example.invalid/image.jpg",
            "list": None,
            "small": None,
        },
        "source_product_url": "https://example.invalid/item",
        "review": {"average": 4.0, "count": 3},
        "observed_at": "2026-10-02T00:00:00Z",
        "data_freshness": "CURRENT",
    }


class EbookComicProjectionCandidateTests(unittest.TestCase):
    def test_valid_structure_never_grants_semantics_or_publication(self):
        result = subject.assess(valid_candidate())
        self.assertEqual(result.status, subject.READY)
        self.assertTrue(result.structure_valid)
        self.assertTrue(result.exact_field_allowlist)
        self.assertFalse(result.contributor_semantics_confirmed)
        self.assertFalse(result.field_rights_confirmed)
        self.assertFalse(result.compliance_approved)
        self.assertFalse(result.publication_allowed)
        self.assertFalse(result.affiliate_activation_allowed)
        self.assertFalse(result.sitemap_change_allowed)
        self.assertFalse(result.production_write_allowed)

    def test_unknown_or_missing_field_fails_closed(self):
        unknown = valid_candidate()
        unknown["description"] = "not allowed"
        missing = valid_candidate()
        del missing["review"]
        for value in (unknown, missing):
            with self.subTest(value=value):
                self.assertEqual(subject.assess(value).status, subject.FAIL_CLOSED)

    def test_namespace_and_public_id_are_exact(self):
        value = valid_candidate()
        value["source"]["site"] = "DMM.com"
        value["public_id"] = "djn_0123456789abcdef01234567"
        self.assertEqual(subject.assess(value).status, subject.FAIL_CLOSED)

    def test_contributor_roles_remain_separate_and_required(self):
        for field in ("authors", "manufactures", "series", "genres"):
            value = valid_candidate()
            value[field] = []
            with self.subTest(field=field):
                result = subject.assess(value)
                self.assertEqual(result.status, subject.FAIL_CLOSED)
                self.assertFalse(result.publication_allowed)

    def test_unsafe_url_naive_timestamp_and_invalid_review_fail_closed(self):
        unsafe = valid_candidate()
        unsafe["source_product_url"] = "javascript:alert(1)"
        naive = valid_candidate()
        naive["observed_at"] = "2026-10-02T00:00:00"
        invalid_review = valid_candidate()
        invalid_review["review"] = {"average": None, "count": 1}
        for value in (unsafe, naive, invalid_review):
            with self.subTest(value=value):
                self.assertEqual(subject.assess(value).status, subject.FAIL_CLOSED)

    def test_review_may_be_fully_unavailable(self):
        value = valid_candidate()
        value["review"] = {"average": None, "count": None}
        self.assertEqual(subject.assess(value).status, subject.READY)


if __name__ == "__main__":
    unittest.main()
