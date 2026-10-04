from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import books_compliance_scope_router as subject  # noqa: E402


def response(scopes=None, groups=subject.QUESTION_GROUPS):
    if scopes is None:
        scopes = subject.KNOWN_SCOPES
    return subject.SanitizedBooksOfficialResponse(
        version=subject.VERSION,
        received_at="2026-10-05T01:00:00+09:00",
        source_type=subject.DIRECT_SUPPORT,
        source_authority="DMM_AFFILIATE_SUPPORT",
        safe_reference="books-scope-response-001",
        explicitly_named_scopes=tuple(subject.BooksScope(*scope) for scope in scopes),
        explicitly_answered_groups=tuple(groups),
    )


class BooksComplianceScopeRouterTests(unittest.TestCase):
    def test_all_explicit_scopes_route_only_to_separate_intakes(self):
        result = subject.route(response())
        self.assertEqual(result.status, subject.READY)
        self.assertTrue(result.category_intake_allowed)
        self.assertFalse(result.compliance_approved)
        self.assertFalse(result.publication_allowed)
        self.assertFalse(result.external_send_allowed)
        self.assertFalse(result.production_write_allowed)

    def test_comic_only_does_not_propagate_to_bl_or_photo(self):
        result = subject.route(response(scopes=(subject.KNOWN_SCOPES[0],)))
        self.assertEqual(result.status, subject.PARTIAL)
        self.assertEqual(result.routed_scopes, (subject.KNOWN_SCOPES[0],))
        self.assertEqual(result.pending_scopes, subject.KNOWN_SCOPES[1:])
        self.assertFalse(result.category_intake_allowed)

    def test_missing_question_group_stays_partial(self):
        result = subject.route(response(groups=subject.QUESTION_GROUPS[:-1]))
        self.assertEqual(result.status, subject.PARTIAL)
        self.assertFalse(result.category_intake_allowed)

    def test_unknown_or_implicit_scope_fails_closed(self):
        unknown = (("FANZA", "ebook", "unknown", "ebook_unknown"),)
        self.assertEqual(subject.route(response(scopes=unknown)).status, subject.FAIL_CLOSED)
        self.assertEqual(subject.route(response(scopes=())).status, subject.FAIL_CLOSED)

    def test_duplicate_groups_and_unsafe_reference_fail_closed(self):
        duplicated = response(groups=("FIELD_USE", "FIELD_USE"))
        self.assertEqual(subject.route(duplicated).status, subject.FAIL_CLOSED)
        value = response()
        unsafe = subject.SanitizedBooksOfficialResponse(
            **{**value.__dict__, "safe_reference": "https://example.invalid/raw"}
        )
        self.assertEqual(subject.route(unsafe).status, subject.FAIL_CLOSED)

    def test_raw_mapping_is_not_accepted(self):
        self.assertEqual(subject.route({"response": "raw"}).status, subject.FAIL_CLOSED)


if __name__ == "__main__":
    unittest.main()
