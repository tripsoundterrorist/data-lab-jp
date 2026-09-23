import copy
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import revenue_mvp_preconnection_followup_status as followup  # noqa: E402
import revenue_mvp_preconnection_official_response_intake as intake  # noqa: E402


def observation(q4=intake.YES, q5=intake.YES):
    return {
        "intake_version": intake.VERSION,
        "source_type": "DIRECT_SUPPORT_CONFIRMATION",
        "source_authority": "DMM_AFFILIATE_SUPPORT",
        "question_states": dict(zip(followup.QUESTION_IDS, (q4, q5))),
    }


class PreconnectionOfficialResponseIntakeTests(unittest.TestCase):
    def test_explicit_yes_or_no_requires_separate_review_and_connection_approval(self):
        for q4 in (intake.YES, intake.NO):
            for q5 in (intake.YES, intake.NO):
                with self.subTest(q4=q4, q5=q5):
                    value = observation(q4, q5)
                    original = copy.deepcopy(value)
                    result = intake.assess_preconnection_official_response(value)
                    self.assertEqual(value, original)
                    self.assertEqual(result.status, intake.REVIEW_REQUIRED)
                    self.assertEqual((result.live_single_request_permission,
                                      result.user_agent_requirement), (q4, q5))
                    self.assertTrue(result.compliance_review_required)
                    self.assertTrue(result.explicit_connection_approval_required)
                    self.assertFalse(result.live_connection_allowed)
                    self.assertFalse(result.gate_unlock_allowed)
                    self.assertEqual(set(result.to_dict()), {
                        "intake_version", "status", "live_single_request_permission",
                        "user_agent_requirement", "live_connection_allowed",
                        "gate_unlock_allowed", "compliance_review_required",
                        "explicit_connection_approval_required", "reason_codes",
                    })

    def test_unanswered_ambiguous_and_contradictory_answers_block(self):
        for question in followup.QUESTION_IDS:
            for state in (intake.UNSPECIFIED, intake.AMBIGUOUS, intake.CONTRADICTORY):
                with self.subTest(question=question, state=state):
                    value = observation()
                    value["question_states"][question] = state
                    result = intake.assess_preconnection_official_response(value)
                    self.assertEqual(result.status, intake.BLOCKED)
                    self.assertEqual(result.reason_codes, ("ANSWER_UNRESOLVED",))
                    self.assertFalse(result.live_connection_allowed)
                    self.assertFalse(result.gate_unlock_allowed)

    def test_unknown_fields_values_versions_and_source_pairs_block_without_echo(self):
        cases = [None, {}, [], {**observation(), "raw_email_body": "private-marker"},
                 {**observation(), "intake_version": "0.2"},
                 {**observation(), "source_type": "UNKNOWN"},
                 {**observation(), "source_authority": "DMM_OFFICIAL_DOCUMENTATION"},
                 {**observation(), "question_states": {followup.QUESTION_IDS[0]: intake.YES}},
                 {**observation(), "question_states": {**observation()["question_states"], "URL": "private-marker"}},
                 observation("MAYBE"), observation(True), observation(1)]
        for value in cases:
            with self.subTest(value_type=type(value)):
                result = intake.assess_preconnection_official_response(value)
                self.assertEqual(result.status, intake.BLOCKED)
                self.assertFalse(result.live_connection_allowed)
                self.assertFalse(result.gate_unlock_allowed)
                rendered = json.dumps(result.to_dict())
                self.assertNotIn("private-marker", rendered)
                self.assertNotIn("raw_email_body", rendered)

    def test_official_documentation_pair_is_accepted_without_content_or_url(self):
        value = observation(intake.NO, intake.YES)
        value["source_type"] = "OFFICIAL_DOCUMENTATION"
        value["source_authority"] = "DMM_OFFICIAL_DOCUMENTATION"
        self.assertEqual(intake.assess_preconnection_official_response(value).status,
                         intake.REVIEW_REQUIRED)

    def test_hostile_unknown_key_is_not_compared_or_rendered(self):
        events = []

        class Hostile:
            def __hash__(self):
                events.append("hash")
                return hash("question_states")

            def __eq__(self, _other):
                events.append("eq")
                raise AssertionError("secret-like-marker")

            def __repr__(self):
                events.append("repr")
                raise AssertionError("secret-like-marker")

        value = {Hostile(): "private-marker"}
        events.clear()
        result = intake.assess_preconnection_official_response(value)
        self.assertEqual(result.status, intake.BLOCKED)
        self.assertEqual(events, [])
        self.assertNotIn("private-marker", repr(result))
        self.assertNotIn("secret-like-marker", repr(result))

    def test_existing_submission_status_is_not_mutated(self):
        before = followup.current_status()
        intake.assess_preconnection_official_response(observation())
        self.assertEqual(followup.current_status(), before)
        self.assertFalse(before.response_received)
        self.assertFalse(before.live_connection_allowed)
        self.assertFalse(before.gate_unlock_allowed)


if __name__ == "__main__":
    unittest.main()
