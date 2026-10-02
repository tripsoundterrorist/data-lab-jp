from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import doujin_seo_url_candidate as subject  # noqa: E402


def evaluate(**changes):
    values = {
        "public_id": "djn_0123456789abcdef01234567",
        "content_type": "doujin",
        "canonical_origin": "https://datalabx.jp",
        "structure_ready": True,
        "rights_confirmed": False,
        "lifecycle_confirmed": False,
        "compliance_approved": False,
        "unique_user_value_confirmed": False,
        "publication_approved": False,
    }
    values.update(changes)
    return subject.evaluate(**values)


class DoujinSeoUrlCandidateTests(unittest.TestCase):
    def test_current_closed_gates_require_noindex(self):
        result = evaluate()
        self.assertEqual(result.status, "NOINDEX_REVIEW_CANDIDATE")
        self.assertTrue(result.route_contract_valid)
        self.assertTrue(result.noindex_required)
        self.assertFalse(result.canonical_candidate)
        self.assertFalse(result.sitemap_candidate)
        self.assertFalse(result.production_write_allowed)

    def test_invalid_id_type_or_origin_fails_closed(self):
        for changes in (
            {"public_id": "itm_0123456789abcdef01234567"},
            {"content_type": "video"},
            {"canonical_origin": "https://example.invalid"},
        ):
            with self.subTest(changes=changes):
                self.assertEqual(evaluate(**changes).status, "FAIL_CLOSED")

    def test_all_future_gates_only_create_review_candidate(self):
        result = evaluate(
            rights_confirmed=True,
            lifecycle_confirmed=True,
            compliance_approved=True,
            unique_user_value_confirmed=True,
            publication_approved=True,
        )
        self.assertEqual(result.status, "SEO_REVIEW_CANDIDATE")
        self.assertTrue(result.canonical_candidate)
        self.assertTrue(result.index_candidate)
        self.assertTrue(result.sitemap_candidate)
        self.assertFalse(result.noindex_required)
        self.assertFalse(result.production_write_allowed)
        self.assertFalse(result.entity_page_candidate)

    def test_non_boolean_gate_fails_closed(self):
        result = evaluate(rights_confirmed=1)
        self.assertEqual(result.status, "NOINDEX_REVIEW_CANDIDATE")
        self.assertFalse(result.index_candidate)


if __name__ == "__main__":
    unittest.main()
