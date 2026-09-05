from pathlib import Path
from types import SimpleNamespace
import json
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_unlock_checklist as gate  # noqa: E402


def release(**overrides):
    values = {
        "status": "BLOCKED",
        "production_smoke_status": "PRODUCTION_SHELL_VALIDATED",
        "official_answer_status": "FAIL_CLOSED",
        "core_official_answer_candidate": False,
        "public_data_deployment_allowed": False,
        "publication_readiness": "BLOCKED",
        "search_console_status": "PUBLIC_SHELL_READY",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class RevenueMvpUnlockChecklistTests(unittest.TestCase):
    def test_current_state_prioritizes_db_then_official_response(self):
        result = gate.build_checklist(release(), None)
        self.assertEqual(result.status, gate.BLOCKED)
        self.assertFalse(result.production_release_allowed)
        self.assertEqual(result.db_handoff_status, gate.NOT_PROVIDED)
        self.assertEqual(result.next_action, "PROVIDE_ORIGINAL_DB_AND_SHA256")
        self.assertEqual(
            result.ordered_blockers,
            (
                "PROVIDE_ORIGINAL_DB_AND_SHA256",
                "WAIT_FOR_DMM_FANZA_CORE_RESPONSE",
                "PREPARE_VALIDATED_PUBLIC_DATA_ARTIFACT",
                "COMPLETE_PUBLICATION_READINESS",
            ),
        )

    def test_failed_db_preflight_stays_first(self):
        db = SimpleNamespace(status="BLOCKED", identity_verified=False)
        result = gate.build_checklist(release(), db)
        self.assertEqual(result.next_action, "FIX_DB_HANDOFF_PREFLIGHT")

    def test_all_evidence_only_reaches_final_approval_candidate(self):
        db = SimpleNamespace(status="HANDOFF_READY", identity_verified=True)
        result = gate.build_checklist(
            release(
                status="READY_FOR_RELEASE_APPROVAL",
                official_answer_status="REVIEW_CANDIDATE",
                core_official_answer_candidate=True,
                public_data_deployment_allowed=True,
                publication_readiness="READY",
            ),
            db,
        )
        self.assertEqual(result.status, gate.READY)
        self.assertEqual(result.next_action, "REQUEST_FINAL_RELEASE_APPROVAL")
        self.assertFalse(result.production_release_allowed)

    def test_production_and_search_failures_are_explicitly_ordered(self):
        db = SimpleNamespace(status="HANDOFF_READY", identity_verified=True)
        result = gate.build_checklist(
            release(
                production_smoke_status="FAIL_CLOSED",
                search_console_status="FAIL_CLOSED",
            ),
            db,
        )
        self.assertEqual(
            result.ordered_blockers[:3],
            (
                "WAIT_FOR_DMM_FANZA_CORE_RESPONSE",
                "RESTORE_PRODUCTION_SHELL",
                "FIX_SEARCH_CONSOLE_GATE",
            ),
        )

    def test_partial_db_arguments_fail_closed_without_leaking_values(self):
        with mock.patch.object(
            gate.revenue_mvp_release_gate, "run_gate"
        ) as release_gate:
            result = gate.run_checklist(
                db_path=Path("/secret/database.db"), expected_sha256=None
            )
        release_gate.assert_not_called()
        self.assertEqual(result.status, gate.FAIL_CLOSED)
        self.assertNotIn("secret", json.dumps(result.to_dict()))

    def test_internal_error_is_bounded(self):
        with mock.patch.object(
            gate.revenue_mvp_release_gate, "run_gate",
            side_effect=RuntimeError("credential value"),
        ):
            result = gate.run_checklist()
        self.assertEqual(result.status, gate.FAIL_CLOSED)
        self.assertNotIn("credential", json.dumps(result.to_dict()))


if __name__ == "__main__":
    unittest.main()
