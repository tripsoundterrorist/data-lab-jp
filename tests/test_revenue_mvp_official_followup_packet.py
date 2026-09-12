from pathlib import Path
import json
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import official_response_intake as intake  # noqa: E402
import revenue_mvp_official_followup_packet as packet  # noqa: E402
from official_blocker_policy import LIFECYCLE_BLOCKER, SORT_BLOCKER  # noqa: E402


class OfficialFollowupPacketTests(unittest.TestCase):
    def test_packet_covers_each_intake_question_exactly_once(self):
        result = packet.build_packet()
        self.assertEqual(tuple(section.blocker_id for section in result.sections),
                         (LIFECYCLE_BLOCKER, SORT_BLOCKER))
        self.assertEqual(result.sections[0].question_ids,
                         intake.LIFECYCLE_QUESTION_IDS)
        self.assertEqual(result.sections[1].question_ids,
                         intake.SORT_QUESTION_IDS)
        all_ids = tuple(q for section in result.sections for q in section.question_ids)
        self.assertEqual(len(all_ids), len(set(all_ids)))

    def test_packet_is_complete_but_never_authorizes_send_or_unlock(self):
        result = packet.build_packet()
        self.assertEqual(len(result.sections[0].questions), 5)
        self.assertEqual(len(result.sections[1].questions), 4)
        self.assertFalse(result.send_authorized)
        self.assertFalse(result.gate_unlock_allowed)

    def test_safe_output_has_no_account_data_or_credentials(self):
        rendered = json.dumps(packet.build_packet().to_dict(), ensure_ascii=False)
        for forbidden in ("api_id=", "affiliate_id=", "password=", "token=", "@"):
            self.assertNotIn(forbidden, rendered.casefold())

    def test_output_contract_is_bounded(self):
        self.assertEqual(
            set(packet.build_packet().to_dict()),
            {"version", "subject", "introduction", "sections", "closing",
             "gate_unlock_allowed", "send_authorized", "reason_codes"},
        )


if __name__ == "__main__":
    unittest.main()
