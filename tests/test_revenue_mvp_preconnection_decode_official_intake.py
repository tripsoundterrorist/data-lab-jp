import copy
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import revenue_mvp_preconnection_decode_official_intake as intake  # noqa: E402
import revenue_mvp_preconnection_followup_status as q4q5_status  # noqa: E402
import revenue_mvp_preconnection_official_response_intake as q4q5_intake  # noqa: E402


def observation(q1=intake.YES, q3=intake.YES):
    return {
        "intake_version": intake.VERSION,
        "source_type": "DIRECT_SUPPORT_CONFIRMATION",
        "source_authority": "DMM_AFFILIATE_SUPPORT",
        "question_states": dict(zip(intake.QUESTION_IDS, (q1, q3))),
    }


class PreconnectionDecodeOfficialIntakeTests(unittest.TestCase):
    def assert_closed(self, result):
        self.assertFalse(result.live_connection_allowed)
        self.assertFalse(result.gate_unlock_allowed)
        self.assertFalse(result.live_decode_profile_approved)
        self.assertTrue(result.compliance_review_required)
        self.assertTrue(result.explicit_connection_approval_required)

    def test_explicit_yes_and_no_are_only_separate_review_candidates(self):
        for q1 in (intake.YES, intake.NO):
            for q3 in (intake.YES, intake.NO):
                with self.subTest(q1=q1, q3=q3):
                    value = observation(q1, q3)
                    original = copy.deepcopy(value)
                    result = intake.assess_preconnection_decode_official_response(value)
                    self.assertEqual(value, original)
                    self.assertEqual(result.status, intake.REVIEW_REQUIRED)
                    self.assertEqual((result.q1_numeric_status_answer,
                                      result.q3_json_utf8_answer), (q1, q3))
                    self.assert_closed(result)
                    self.assertEqual(set(result.to_dict()), {
                        "intake_version", "status", "q1_numeric_status_answer",
                        "q3_json_utf8_answer", "live_connection_allowed",
                        "gate_unlock_allowed", "live_decode_profile_approved",
                        "compliance_review_required", "explicit_connection_approval_required",
                        "reason_codes",
                    })

    def test_unanswered_ambiguous_and_contradictory_states_block(self):
        for question in intake.QUESTION_IDS:
            for state in (intake.UNSPECIFIED, intake.AMBIGUOUS, intake.CONTRADICTORY):
                with self.subTest(question=question, state=state):
                    value = observation()
                    value["question_states"][question] = state
                    result = intake.assess_preconnection_decode_official_response(value)
                    self.assertEqual(result.status, intake.BLOCKED)
                    self.assertEqual(result.reason_codes, ("ANSWER_UNRESOLVED",))
                    self.assert_closed(result)

    def test_missing_unknown_version_source_and_non_enum_values_block(self):
        cases = [None, {}, [], {**observation(), "raw_answer": "private-marker"},
                 {**observation(), "intake_version": "0.2"},
                 {**observation(), "source_type": "INTERNAL_OBSERVATION"},
                 {**observation(), "source_authority": "DMM_OFFICIAL_DOCUMENTATION"},
                 {**observation(), "question_states": {intake.QUESTION_IDS[0]: intake.YES}},
                 {**observation(), "question_states": {**observation()["question_states"], "header": "private-marker"}},
                 observation("MAYBE"), observation(True), observation(200)]
        for value in cases:
            with self.subTest(value_type=type(value)):
                result = intake.assess_preconnection_decode_official_response(value)
                self.assertEqual(result.status, intake.BLOCKED)
                self.assert_closed(result)
                rendered = json.dumps(result.to_dict())
                self.assertNotIn("private-marker", rendered)
                self.assertNotIn("raw_answer", rendered)

    def test_official_documentation_pair_is_a_review_candidate(self):
        value = observation(intake.NO, intake.YES)
        value["source_type"] = "OFFICIAL_DOCUMENTATION"
        value["source_authority"] = "DMM_OFFICIAL_DOCUMENTATION"
        result = intake.assess_preconnection_decode_official_response(value)
        self.assertEqual(result.status, intake.REVIEW_REQUIRED)
        self.assert_closed(result)

    def test_hostile_unknown_key_is_not_compared_or_rendered(self):
        events = []

        class Hostile:
            def __hash__(self):
                events.append("hash")
                return hash("question_states")

            def __eq__(self, _other):
                events.append("eq")
                raise AssertionError("private-marker")

            def __repr__(self):
                events.append("repr")
                raise AssertionError("private-marker")

        value = {Hostile(): "private-marker"}
        events.clear()
        result = intake.assess_preconnection_decode_official_response(value)
        self.assertEqual(result.status, intake.BLOCKED)
        self.assertEqual(events, [])
        self.assertNotIn("private-marker", repr(result))

    def test_existing_q4_q5_contracts_are_unchanged(self):
        previous_status = q4q5_status.current_status()
        prior = {
            "intake_version": q4q5_intake.VERSION,
            "source_type": "DIRECT_SUPPORT_CONFIRMATION",
            "source_authority": "DMM_AFFILIATE_SUPPORT",
            "question_states": dict.fromkeys(q4q5_status.QUESTION_IDS, q4q5_intake.YES),
        }
        previous_result = q4q5_intake.assess_preconnection_official_response(prior)
        intake.assess_preconnection_decode_official_response(observation())
        self.assertEqual(q4q5_status.current_status(), previous_status)
        self.assertEqual(q4q5_intake.assess_preconnection_official_response(prior), previous_result)
        self.assertFalse(previous_status.response_received)


if __name__ == "__main__":
    unittest.main()
