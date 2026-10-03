from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import ebook_bl_projection_candidate as subject  # noqa: E402


def valid_candidate():
    return {
        "projection_version": subject.VERSION,
        "public_id": "ebl_0123456789abcdef01234567",
        "source": {
            "site": "FANZA",
            "service": "ebook",
            "floor": "bl",
            "content_type": "ebook_bl",
            "content_id": "fixture-content",
        },
        "title": "Fixture title",
        "release_date_raw": "2026-01-01 00:00:00",
        "current_price": 100,
        "list_price": None,
        "authors": [{"id": "author-1", "name": "Fixture author"}],
        "manufactures": [{"id": "source-1", "name": "Fixture source"}],
        "series": [{"id": "series-1", "name": "Fixture series"}],
        "genres": [{"id": "genre-1", "name": "Fixture genre"}],
        "source_product_url": f"https://{subject.PRODUCT_HOST}/item",
        "review": {"average": 4.0, "count": 3},
        "observed_at": "2026-10-03T00:00:00+09:00",
        "data_freshness": "CURRENT",
    }


class EbookBlProjectionCandidateTests(unittest.TestCase):
    def test_valid_structure_excludes_image_and_never_grants_publication(self):
        result = subject.assess(valid_candidate())
        self.assertEqual(result.status, subject.READY)
        self.assertTrue(result.structure_valid)
        self.assertTrue(result.exact_field_allowlist)
        self.assertTrue(result.image_field_absent)
        self.assertFalse(result.contributor_semantics_confirmed)
        self.assertFalse(result.field_rights_confirmed)
        self.assertFalse(result.compliance_approved)
        self.assertFalse(result.publication_allowed)
        self.assertFalse(result.affiliate_activation_allowed)
        self.assertFalse(result.sitemap_change_allowed)
        self.assertFalse(result.production_write_allowed)

    def test_sensitive_or_unknown_fields_fail_closed(self):
        for field, value in (
            ("image", {"large": "https://example.invalid/image.jpg"}),
            ("product_description", "not allowed"),
            ("affiliate_url", "https://example.invalid/affiliate"),
            ("raw_api_response", {"secret": "not allowed"}),
        ):
            candidate = valid_candidate()
            candidate[field] = value
            with self.subTest(field=field):
                self.assertEqual(subject.assess(candidate).status, subject.FAIL_CLOSED)

    def test_missing_field_fails_closed(self):
        candidate = valid_candidate()
        del candidate["genres"]
        self.assertEqual(subject.assess(candidate).status, subject.FAIL_CLOSED)

    def test_namespace_public_id_and_product_host_are_exact(self):
        namespace = valid_candidate()
        namespace["source"]["floor"] = "comic"
        public_id = valid_candidate()
        public_id["public_id"] = "ebc_0123456789abcdef01234567"
        host = valid_candidate()
        host["source_product_url"] = "https://example.invalid/item"
        credential = valid_candidate()
        credential["source_product_url"] = (
            f"https://user:password@{subject.PRODUCT_HOST}/item"
        )
        for value in (namespace, public_id, host, credential):
            with self.subTest(value=value):
                self.assertEqual(subject.assess(value).status, subject.FAIL_CLOSED)

    def test_entity_roles_remain_separate_and_required(self):
        for field in ("authors", "manufactures", "series", "genres"):
            candidate = valid_candidate()
            candidate[field] = []
            with self.subTest(field=field):
                self.assertEqual(subject.assess(candidate).status, subject.FAIL_CLOSED)

    def test_review_must_be_complete_or_fully_unavailable(self):
        missing = valid_candidate()
        missing["review"] = {"average": None, "count": None}
        incomplete = valid_candidate()
        incomplete["review"] = {"average": None, "count": 1}
        invalid = valid_candidate()
        invalid["review"] = {"average": float("nan"), "count": 1}
        self.assertEqual(subject.assess(missing).status, subject.READY)
        self.assertEqual(subject.assess(incomplete).status, subject.FAIL_CLOSED)
        self.assertEqual(subject.assess(invalid).status, subject.FAIL_CLOSED)

    def test_timestamp_requires_timezone(self):
        candidate = valid_candidate()
        candidate["observed_at"] = "2026-10-03T00:00:00"
        self.assertEqual(subject.assess(candidate).status, subject.FAIL_CLOSED)


if __name__ == "__main__":
    unittest.main()
