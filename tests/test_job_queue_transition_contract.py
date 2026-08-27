from dataclasses import FrozenInstanceError, asdict, replace
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import unattended_job_queue as queue
from tests.test_unattended_job_queue import job, checkpoint


class TransitionContractTests(unittest.TestCase):
    def pending(self):
        return job(requires_approval=True)

    def apply(self, value=None, flag=False):
        return queue.apply_approval_with_transition(self.pending() if value is None else value,
                                                     approval_event_received=flag)

    def test_version(self):
        self.assertEqual(queue.TRANSITION_VERSION, "0.1")

    def test_schema(self):
        _, result = self.apply()
        self.assertEqual(set(result.to_dict()), {
            "transition_version", "job_id", "job_type", "previous_state", "new_state",
            "occurred_at", "transition_status", "reason_code"})

    def test_job_identity(self):
        original = self.pending()
        updated, result = self.apply(original)
        self.assertEqual((result.job_id, result.job_type), (original.job_id, original.job_type))
        self.assertEqual(updated.job_id, original.job_id)

    def test_states(self):
        _, result = self.apply()
        self.assertEqual((result.previous_state, result.new_state), (queue.READY, queue.WAITING_APPROVAL))
        self.assertEqual(result.transition_status, "APPLIED")

    def test_once_utc_timestamp(self):
        fixed = datetime(2026, 8, 27, 12, 1, 2, 123456, tzinfo=timezone.utc)
        with mock.patch.object(queue, "datetime", wraps=datetime) as clock:
            clock.now.return_value = fixed
            _, result = self.apply()
            for _ in range(5):
                self.assertEqual(result.to_dict()["occurred_at"], "2026-08-27T12:01:02.123456Z")
            clock.now.assert_called_once_with(timezone.utc)

    def test_immutable(self):
        updated, result = self.apply()
        with self.assertRaises(FrozenInstanceError):
            result.new_state = queue.DONE
        with self.assertRaises(FrozenInstanceError):
            updated.state = queue.DONE

    def test_serialization_copy(self):
        _, result = self.apply()
        view = result.to_dict()
        view["occurred_at"] = "changed"
        self.assertNotEqual(view, result.to_dict())

    def test_original_unchanged(self):
        original = self.pending()
        before = asdict(original)
        updated, _ = self.apply(original)
        self.assertEqual(asdict(original), before)
        self.assertEqual(updated.created_at, original.created_at)
        self.assertFalse(original.approval_received)

    def test_explicit_approval(self):
        original = job(state=queue.WAITING_APPROVAL, requires_approval=True)
        updated, result = self.apply(original, True)
        self.assertEqual(updated, queue.apply_approval(original, approval_event_received=True))
        self.assertTrue(updated.approval_received)
        self.assertEqual(result.new_state, queue.READY)

    def test_unchanged_no_timestamp(self):
        original = job(state=queue.WAITING_APPROVAL, requires_approval=True)
        with mock.patch.object(queue, "datetime", wraps=datetime) as clock:
            updated, result = self.apply(original)
            clock.now.assert_not_called()
        self.assertEqual(result.transition_status, "UNCHANGED")
        self.assertIsNone(result.occurred_at)
        self.assertEqual(updated, original)

    def test_non_boolean_rejected(self):
        for flag in (None, 1, "true", {}, []):
            updated, result = self.apply(flag=flag)
            self.assertIsNone(updated)
            self.assertEqual(result.transition_status, "REJECTED")

    def test_bad_identity_not_echoed(self):
        updated, result = self.apply(job(job_id="fixture-secret"))
        self.assertIsNone(updated)
        self.assertNotIn("fixture-secret", json.dumps(result.to_dict()))

    def test_unknown_state(self):
        updated, result = self.apply(job(state="UNKNOWN"))
        self.assertIsNone(updated)
        self.assertIsNone(result.new_state)

    def test_invalid_contract(self):
        for value in ({}, "fixture-secret", None):
            updated, result = queue.apply_approval_with_transition(value, approval_event_received=False)
            self.assertIsNone(updated)
            self.assertEqual(result.transition_status, "REJECTED")

    def test_valid_transition(self):
        original = self.pending()
        updated, _ = self.apply(original)
        self.assertTrue(queue.validate_approval_transition(original, updated, approval_event_received=False))

    def test_invalid_pair(self):
        original = self.pending()
        self.assertFalse(queue.validate_approval_transition(original, replace(original, state=queue.DONE),
                                                            approval_event_received=False))

    def test_completion_not_invented(self):
        original = job(state=queue.RUNNING)
        self.assertFalse(queue.validate_approval_transition(original, replace(original, state=queue.DONE),
                                                            approval_event_received=False))
        self.assertTrue(queue.validate_job(replace(original, state=queue.DONE))[0])

    def test_same_pair_different_metadata_rejected(self):
        original = self.pending()
        updated, _ = self.apply(original)
        self.assertFalse(queue.validate_approval_transition(original, replace(updated, priority="P0"),
                                                            approval_event_received=False))

    def test_same_state_not_transition(self):
        original = self.pending()
        self.assertFalse(queue.validate_approval_transition(original, original, approval_event_received=True))

    def test_core_exception(self):
        with mock.patch.object(queue, "apply_approval", side_effect=ValueError("fixture-secret")):
            updated, result = self.apply()
        self.assertIsNone(updated)
        self.assertNotIn("fixture-secret", repr(result))

    def test_invalid_core_output(self):
        with mock.patch.object(queue, "apply_approval", return_value=job(state="UNKNOWN")):
            updated, result = self.apply()
        self.assertIsNone(updated)
        self.assertEqual(result.transition_status, "REJECTED")

    def test_clock_failure(self):
        original = self.pending()
        with mock.patch.object(queue, "datetime", wraps=datetime) as clock:
            clock.now.side_effect = ValueError("fixture-secret")
            updated, result = self.apply(original)
        self.assertIsNone(updated)
        self.assertEqual(original.state, queue.READY)
        self.assertEqual(result.transition_status, "REJECTED")

    def test_legacy_job_schema_unchanged(self):
        self.assertNotIn("state_updated_at", asdict(job()))
        self.assertEqual(len(asdict(job())), 16)

    def test_queue_decision_unchanged(self):
        result = queue.select_next_job([])
        self.assertEqual(result.status, "QUEUE_IDLE")
        self.assertEqual(set(result.to_dict()), {"queue_version", "status", "selected_job_id", "action", "reason_codes"})

    def test_blocked_jobs_remain_idle(self):
        self.assertEqual(queue.select_next_job([job(state=queue.BLOCKED)]).status, "QUEUE_IDLE")

    def test_priority_unchanged(self):
        self.assertEqual(queue.select_next_job([job("a", priority="P3"), job("b", priority="P0")]).selected_job_id, "b")

    def test_failed_safe_retry_unchanged(self):
        self.assertEqual(queue.assess_retry(job(), "POLICY_VIOLATION").state, queue.FAILED_SAFE)

    def test_done_selection_unchanged(self):
        self.assertEqual(queue.select_next_job([job(state=queue.DONE)]).status, "QUEUE_IDLE")

    def test_checkpoint_unchanged(self):
        value = checkpoint()
        before = value.to_dict()
        self.apply()
        self.assertEqual(value.to_dict(), before)

    def test_no_io(self):
        with mock.patch("builtins.open", side_effect=AssertionError()), mock.patch.object(Path, "open", side_effect=AssertionError()):
            self.assertEqual(self.apply()[1].transition_status, "APPLIED")


if __name__ == "__main__":
    unittest.main()
