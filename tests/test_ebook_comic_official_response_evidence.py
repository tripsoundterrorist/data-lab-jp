import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import books_compliance_category_intake_adapter as adapter  # noqa: E402
import books_compliance_scope_router as router  # noqa: E402
import ebook_comic_compliance_response_intake as intake  # noqa: E402


EVIDENCE = ROOT / "docs/evidence/ebook-comic-official-response-sanitized-20261005.json"


def load_result():
    payload = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    exact = payload["exact_scope"]
    scope = router.BooksScope(
        exact["site"], exact["service"], exact["floor"], exact["content_type"]
    )
    response = router.SanitizedBooksOfficialResponse(
        version=payload["version"],
        received_at=payload["received_at"],
        source_type=payload["source_type"],
        source_authority=payload["source_authority"],
        safe_reference=payload["safe_reference"],
        explicitly_named_scopes=(scope,),
        explicitly_answered_groups=tuple(payload["group_states"]),
    )
    request = adapter.BooksCategoryIntakeRequest(
        response=response, group_states=payload["group_states"]
    )
    return payload, adapter.adapt(request, scope)


class EbookComicOfficialResponseEvidenceTests(unittest.TestCase):
    def test_sanitized_evidence_routes_only_to_comic_partial_intake(self):
        payload, result = load_result()
        self.assertEqual(result.status, adapter.ADAPTED)
        self.assertEqual(result.routing_status, router.PARTIAL)
        self.assertEqual(result.intake_status, intake.PARTIAL)
        self.assertEqual(result.resolved_group_count, 3)
        self.assertEqual(result.unresolved_group_count, 1)
        self.assertFalse(result.separate_compliance_decision_candidate)
        self.assertFalse(result.compliance_approved)
        self.assertFalse(result.publication_allowed)
        self.assertFalse(result.external_send_allowed)
        self.assertFalse(result.production_write_allowed)
        self.assertFalse(payload["raw_response_stored"])

    def test_contributor_semantics_do_not_imply_display_permission(self):
        payload, _ = load_result()
        self.assertEqual(payload["confirmed_semantics"]["author"], "AUTHOR_NAME")
        self.assertEqual(
            payload["confirmed_semantics"]["manufacture"], "PUBLISHER_NAME"
        )
        self.assertEqual(payload["group_states"]["CONTRIBUTOR"], intake.UNRESOLVED)
        self.assertIn(
            "CONTRIBUTOR_NAME_DISPLAY_PERMISSION_NOT_EXPLICIT",
            payload["unresolved_points"],
        )

    def test_image_permission_is_conditioned_and_non_publishing(self):
        payload, _ = load_result()
        image = payload["image_requirements"]
        self.assertTrue(image["product_main_image_listed_as_usable"])
        self.assertTrue(image["resize_only"])
        self.assertFalse(image["crop_or_overlay_allowed"])
        self.assertTrue(image["service_specific_restrictions_apply"])
        self.assertFalse(payload["publication_allowed"])
        self.assertFalse(payload["affiliate_activation_allowed"])
        self.assertFalse(payload["database_write_allowed"])


if __name__ == "__main__":
    unittest.main()
