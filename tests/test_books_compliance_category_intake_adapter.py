from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import books_compliance_category_intake_adapter as subject  # noqa: E402
import books_compliance_scope_router as router  # noqa: E402
import ebook_comic_compliance_response_intake as comic  # noqa: E402


def request(scopes, groups=router.QUESTION_GROUPS, state=comic.ALLOW):
    response = router.SanitizedBooksOfficialResponse(
        version=router.VERSION,
        received_at="2026-10-05T02:00:00+09:00",
        source_type=router.DIRECT_SUPPORT,
        source_authority="DMM_AFFILIATE_SUPPORT",
        safe_reference="books-scope-response-002",
        explicitly_named_scopes=tuple(router.BooksScope(*scope) for scope in scopes),
        explicitly_answered_groups=tuple(groups),
    )
    return subject.BooksCategoryIntakeRequest(
        response=response,
        group_states={group: state for group in groups},
    )


class BooksComplianceCategoryIntakeAdapterTests(unittest.TestCase):
    def test_each_explicit_scope_reaches_only_its_category_intake(self):
        for scope in router.KNOWN_SCOPES:
            with self.subTest(scope=scope):
                result = subject.adapt(request((scope,)), router.BooksScope(*scope))
                self.assertEqual(result.status, subject.ADAPTED)
                self.assertEqual(result.intake_status, comic.COMPLETE)
                self.assertTrue(result.separate_compliance_decision_candidate)
                self.assertFalse(result.compliance_approved)
                self.assertFalse(result.publication_allowed)
                self.assertFalse(result.external_send_allowed)
                self.assertFalse(result.production_write_allowed)

    def test_comic_response_cannot_reach_bl_intake(self):
        value = request((router.KNOWN_SCOPES[0],))
        result = subject.adapt(value, router.BooksScope(*router.KNOWN_SCOPES[1]))
        self.assertEqual(result.status, subject.BLOCKED)
        self.assertIn("TARGET_SCOPE_NOT_EXPLICIT", result.reason_codes)

    def test_missing_group_becomes_unresolved_in_category_intake(self):
        groups = router.QUESTION_GROUPS[:-1]
        scope = router.KNOWN_SCOPES[0]
        result = subject.adapt(request((scope,), groups=groups), router.BooksScope(*scope))
        self.assertEqual(result.status, subject.ADAPTED)
        self.assertEqual(result.intake_status, comic.PARTIAL)
        self.assertEqual(result.unresolved_group_count, 1)
        self.assertFalse(result.separate_compliance_decision_candidate)

    def test_contradiction_reaches_category_intake_without_approval(self):
        scope = router.KNOWN_SCOPES[2]
        result = subject.adapt(
            request((scope,), state=comic.CONFLICT), router.BooksScope(*scope)
        )
        self.assertEqual(result.status, subject.ADAPTED)
        self.assertEqual(result.intake_status, comic.CONTRADICTORY)
        self.assertEqual(result.contradictory_group_count, 4)
        self.assertFalse(result.separate_compliance_decision_candidate)

    def test_state_keys_must_match_explicit_groups(self):
        value = request((router.KNOWN_SCOPES[0],))
        malformed = subject.BooksCategoryIntakeRequest(
            response=value.response,
            group_states={router.QUESTION_GROUPS[0]: comic.ALLOW},
        )
        result = subject.adapt(malformed, router.BooksScope(*router.KNOWN_SCOPES[0]))
        self.assertEqual(result.status, subject.BLOCKED)
        self.assertIn("GROUP_STATE_SET_INVALID", result.reason_codes)

    def test_unknown_target_and_raw_input_fail_closed(self):
        unknown = router.BooksScope("FANZA", "ebook", "tl", "ebook_tl")
        self.assertEqual(
            subject.adapt(request((router.KNOWN_SCOPES[0],)), unknown).status,
            subject.BLOCKED,
        )
        self.assertEqual(subject.adapt({}, unknown).status, subject.BLOCKED)


if __name__ == "__main__":
    unittest.main()
