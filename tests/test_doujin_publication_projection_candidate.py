from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import doujin_publication_projection_candidate as subject  # noqa: E402


def valid_candidate() -> dict:
    return {
        "projection_version": "0.1",
        "public_id": "djn_0123456789abcdef01234567",
        "source": {
            "site": "example-site",
            "service": "example-service",
            "floor": "example-floor",
            "content_type": "doujin",
            "content_id": "example-content",
        },
        "title": "Example title",
        "release_date_raw": "2026-01-01",
        "current_price": 100,
        "list_price": 200,
        "discount_amount": 100,
        "discount_rate": 50.0,
        "makers": [{"id": "maker-1", "name": "Example maker"}],
        "series": [],
        "genres": [{"id": "genre-1", "name": "Example genre"}],
        "image": {"large": "https://example.invalid/image.jpg", "list": None, "small": None},
        "source_product_url": "https://example.invalid/item",
        "observed_at": "2026-10-02T00:00:00Z",
        "data_freshness": "CURRENT",
    }


class DoujinPublicationProjectionCandidateTests(unittest.TestCase):
    def test_exact_candidate_is_structure_ready_but_never_publishable(self):
        result = subject.assess(valid_candidate())
        self.assertEqual(result.status, subject.READY)
        self.assertTrue(result.structure_valid)
        self.assertFalse(result.field_rights_confirmed)
        self.assertFalse(result.publication_allowed)
        self.assertFalse(result.affiliate_activation_allowed)
        self.assertFalse(result.sitemap_change_allowed)
        self.assertFalse(result.production_write_allowed)

    def test_unknown_field_fails_closed(self):
        candidate = valid_candidate()
        candidate["review"] = {"count": 1}
        result = subject.assess(candidate)
        self.assertEqual(result.status, subject.FAIL_CLOSED)
        self.assertEqual(result.reason_codes, ("PROJECTION_FIELD_ALLOWLIST_MISMATCH",))

    def test_missing_maker_or_genre_fails_closed(self):
        candidate = valid_candidate()
        candidate["makers"] = []
        result = subject.assess(candidate)
        self.assertEqual(result.status, subject.FAIL_CLOSED)
        self.assertFalse(result.publication_allowed)

    def test_wrong_namespace_and_id_fail_closed(self):
        candidate = valid_candidate()
        candidate["source"]["content_type"] = "video"
        candidate["public_id"] = "itm_unsafe"
        result = subject.assess(candidate)
        self.assertEqual(result.status, subject.FAIL_CLOSED)

    def test_unsafe_url_and_non_scalar_entity_id_fail_closed(self):
        candidate = valid_candidate()
        candidate["source_product_url"] = "javascript:alert(1)"
        candidate["makers"][0]["id"] = None
        result = subject.assess(candidate)
        self.assertEqual(result.status, subject.FAIL_CLOSED)


if __name__ == "__main__":
    unittest.main()
