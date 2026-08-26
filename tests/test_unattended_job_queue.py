from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import unattended_job_queue as queue  # noqa: E402


NOW = "2026-08-27T00:00:00+09:00"


def job(job_id="job-a", **changes):
    value = queue.JobContract(
        queue_version="0.1", job_id=job_id, job_type="static_validation",
        priority="P2", risk_class=queue.READ_ONLY, dependencies=(),
        blocker_codes=(), requires_approval=False, retry_policy="TRANSIENT_ONLY",
        max_attempts=3, checkpoint_supported=True,
        created_at="2026-08-26T00:00:00+09:00", deadline_class="NONE",
    )
    return replace(value, **changes)


def checkpoint(value=None, **changes):
    base = queue.create_checkpoint(
        value or job(), last_completed_step="STEP_ONE",
        resume_preconditions=("GIT_CLEAN",), checkpoint_time=NOW,
        reason_codes=("SAFE_PAUSE",),
    )
    assert base is not None
    return replace(base, **changes)


def event(**changes):
    values = {
        "event_version": "0.1", "event_type": "JOB_COMPLETED",
        "job_id": "job-a", "job_type": "static_validation",
        "severity": "INFO", "state": "DONE", "approval_required": False,
        "summary_code": "JOB_COMPLETED_SAFE", "occurred_at": NOW,
    }
    values.update(changes)
    return queue.create_event(**values)


class UnattendedJobQueueTests(unittest.TestCase):
    def test_01_version(self): self.assertEqual(queue.QUEUE_VERSION, "0.1")
    def test_02_ready_selection(self): self.assertEqual(queue.select_next_job([job()]).selected_job_id, "job-a")
    def test_03_priority_order(self): self.assertEqual(queue.select_next_job([job("p2"), job("p1", priority="P1")]).selected_job_id, "p1")
    def test_04_deterministic_tie_id(self): self.assertEqual(queue.select_next_job([job("b"), job("a")]).selected_job_id, "a")
    def test_05_deterministic_created_at(self): self.assertEqual(queue.select_next_job([job("a"), job("b", created_at="2026-08-25T00:00:00Z")]).selected_job_id, "b")
    def test_06_dependency_done(self): self.assertEqual(queue.select_next_job([job("dep", state=queue.DONE), job("work", dependencies=("dep",))]).selected_job_id, "work")
    def test_07_dependency_incomplete(self): self.assertIsNone(queue.select_next_job([job("dep", state=queue.RUNNING), job("work", dependencies=("dep",))]).selected_job_id)
    def test_08_blocked_skipped(self): self.assertEqual(queue.select_next_job([job("x", state=queue.BLOCKED), job("y")]).selected_job_id, "y")
    def test_09_blocker_code_skipped(self): self.assertIsNone(queue.select_next_job([job(blocker_codes=("POLICY_BLOCK",))]).selected_job_id)
    def test_10_waiting_skipped(self): self.assertIsNone(queue.select_next_job([job(state=queue.WAITING_APPROVAL)]).selected_job_id)
    def test_11_retry_wait_skipped(self): self.assertIsNone(queue.select_next_job([job(state=queue.RETRY_WAIT)]).selected_job_id)
    def test_12_failed_safe_skipped(self): self.assertIsNone(queue.select_next_job([job(state=queue.FAILED_SAFE)]).selected_job_id)
    def test_13_checkpointed_skipped(self): self.assertIsNone(queue.select_next_job([job(state=queue.CHECKPOINTED)]).selected_job_id)
    def test_14_done_skipped(self): self.assertIsNone(queue.select_next_job([job(state=queue.DONE)]).selected_job_id)
    def test_15_cancelled_skipped(self): self.assertIsNone(queue.select_next_job([job(state=queue.CANCELLED)]).selected_job_id)
    def test_16_read_only_allowed(self): self.assertIsNotNone(queue.select_next_job([job(risk_class=queue.READ_ONLY)]).selected_job_id)
    def test_17_low_risk_allowed(self): self.assertIsNotNone(queue.select_next_job([job(risk_class=queue.LOW_RISK_LOCAL)]).selected_job_id)
    def test_18_external_default_blocked(self): self.assertIsNone(queue.select_next_job([job(risk_class=queue.EXTERNAL_READ)]).selected_job_id)
    def test_19_external_explicit_allowed(self): self.assertIsNotNone(queue.select_next_job([job(risk_class=queue.EXTERNAL_READ)], external_read_allowed=True).selected_job_id)
    def test_20_approval_required_blocked(self): self.assertIsNone(queue.select_next_job([job(risk_class=queue.APPROVAL_REQUIRED, requires_approval=True)]).selected_job_id)
    def test_21_prohibited_ready_blocks_queue(self): self.assertEqual(queue.select_next_job([job(risk_class=queue.PROHIBITED_UNATTENDED)]).status, "QUEUE_BLOCKED")
    def test_22_approval_without_event_waits(self): self.assertEqual(queue.apply_approval(job(requires_approval=True, risk_class=queue.APPROVAL_REQUIRED), approval_event_received=False).state, queue.WAITING_APPROVAL)
    def test_23_approval_event_received(self): self.assertTrue(queue.apply_approval(job(requires_approval=True, risk_class=queue.APPROVAL_REQUIRED), approval_event_received=True).approval_received)
    def test_24_approved_job_selected(self): self.assertIsNotNone(queue.select_next_job([job(requires_approval=True, approval_received=True, risk_class=queue.APPROVAL_REQUIRED)]).selected_job_id)
    def test_25_blocked_switch(self): self.assertEqual(queue.switch_after_pause("x", [job("x", state=queue.BLOCKED), job("y")]).action, "SWITCH_TO_NEXT_JOB")
    def test_26_waiting_switch(self): self.assertEqual(queue.switch_after_pause("x", [job("x", state=queue.WAITING_APPROVAL), job("y")]).selected_job_id, "y")
    def test_27_retry_switch(self): self.assertEqual(queue.switch_after_pause("x", [job("x", state=queue.RETRY_WAIT), job("y")]).selected_job_id, "y")
    def test_28_checkpoint_switch(self): self.assertEqual(queue.switch_after_pause("x", [job("x", state=queue.CHECKPOINTED), job("y")]).selected_job_id, "y")
    def test_29_failed_switch(self): self.assertEqual(queue.switch_after_pause("x", [job("x", state=queue.FAILED_SAFE), job("y")]).selected_job_id, "y")
    def test_30_no_ready_idle(self): self.assertEqual(queue.switch_after_pause("x", [job("x", state=queue.BLOCKED)]).status, "QUEUE_IDLE")
    def test_31_running_not_switchable(self): self.assertEqual(queue.switch_after_pause("x", [job("x", state=queue.RUNNING)]).status, "QUEUE_BLOCKED")
    def test_32_checkpoint_schema(self): self.assertEqual(set(checkpoint().to_dict()), {"job_id", "state", "last_completed_step", "resume_preconditions", "blocker_codes", "attempt_count", "checkpoint_time", "reason_codes"})
    def test_33_checkpoint_secret_reject(self): self.assertFalse(queue.validate_checkpoint(checkpoint(last_completed_step="secret"))[0])
    def test_34_checkpoint_url_reject(self): self.assertFalse(queue.validate_checkpoint(checkpoint(last_completed_step="https://example.invalid"))[0])
    def test_35_checkpoint_path_reject(self): self.assertFalse(queue.validate_checkpoint(checkpoint(last_completed_step="C:/private"))[0])
    def test_36_checkpoint_raw_exception_reject(self): self.assertFalse(queue.validate_checkpoint(checkpoint(last_completed_step="raw_exception"))[0])
    def test_37_checkpoint_malformed(self): self.assertFalse(queue.validate_checkpoint({})[0])
    def test_38_resume_allowed(self): self.assertTrue(queue.resume_from_checkpoint(job(state=queue.CHECKPOINTED), checkpoint(), now="2026-08-27T00:01:00+09:00", dependency_states={}, environment_preflight_passed=True).resume_allowed)
    def test_39_resume_dependency_recheck(self): self.assertEqual(queue.resume_from_checkpoint(job(state=queue.CHECKPOINTED, dependencies=("dep",)), checkpoint(job(dependencies=("dep",))), now="2026-08-27T00:01:00+09:00", dependency_states={"dep": queue.READY}, environment_preflight_passed=True).status, queue.BLOCKED)
    def test_40_resume_blocker_recheck(self): self.assertEqual(queue.resume_from_checkpoint(job(state=queue.CHECKPOINTED, blocker_codes=("BLOCK",)), checkpoint(job(blocker_codes=("BLOCK",))), now="2026-08-27T00:01:00+09:00", dependency_states={}, environment_preflight_passed=True).status, queue.BLOCKED)
    def test_41_resume_approval_recheck(self): self.assertEqual(queue.resume_from_checkpoint(job(state=queue.CHECKPOINTED, requires_approval=True, risk_class=queue.APPROVAL_REQUIRED), checkpoint(job(requires_approval=True, risk_class=queue.APPROVAL_REQUIRED)), now="2026-08-27T00:01:00+09:00", dependency_states={}, environment_preflight_passed=True).status, queue.WAITING_APPROVAL)
    def test_42_resume_environment_recheck(self): self.assertEqual(queue.resume_from_checkpoint(job(state=queue.CHECKPOINTED), checkpoint(), now="2026-08-27T00:01:00+09:00", dependency_states={}, environment_preflight_passed=False).status, queue.BLOCKED)
    def test_43_stale_checkpoint(self): self.assertEqual(queue.resume_from_checkpoint(job(state=queue.CHECKPOINTED), checkpoint(), now="2026-08-29T00:00:01+09:00", dependency_states={}, environment_preflight_passed=True).status, queue.FAILED_SAFE)
    def test_43b_non_checkpointed_resume_rejected(self): self.assertEqual(queue.resume_from_checkpoint(job(), checkpoint(), now="2026-08-27T00:01:00+09:00", dependency_states={}, environment_preflight_passed=True).status, queue.FAILED_SAFE)
    def test_44_retry_network(self): self.assertTrue(queue.assess_retry(job(), "TEMPORARY_NETWORK_FAILURE").retry_allowed)
    def test_45_retry_file_lock(self): self.assertTrue(queue.assess_retry(job(), "TRANSIENT_FILE_LOCK").retry_allowed)
    def test_46_retry_local(self): self.assertTrue(queue.assess_retry(job(retry_policy="EXPLICIT_LOCAL"), "RETRYABLE_LOCAL_ERROR").retry_allowed)
    def test_47_auth_no_retry(self): self.assertFalse(queue.assess_retry(job(), "AUTHENTICATION_FAILURE").retry_allowed)
    def test_48_permission_no_retry(self): self.assertFalse(queue.assess_retry(job(), "PERMISSION_DENIED").retry_allowed)
    def test_49_gate_no_retry(self): self.assertFalse(queue.assess_retry(job(), "GATE_CONFLICT").retry_allowed)
    def test_50_secret_no_retry(self): self.assertFalse(queue.assess_retry(job(), "SECRET_ERROR").retry_allowed)
    def test_51_max_attempts(self): self.assertEqual(queue.assess_retry(job(attempt_count=3), "TEMPORARY_NETWORK_FAILURE").state, queue.FAILED_SAFE)
    def test_52_p0_before_p1(self): self.assertEqual(queue.select_next_job([job("p1", priority="P1"), job("p0", priority="P0")]).selected_job_id, "p0")
    def test_53_p1_before_p2(self): self.assertEqual(queue.select_next_job([job("p2", priority="P2"), job("p1", priority="P1")]).selected_job_id, "p1")
    def test_54_p2_before_p3(self): self.assertEqual(queue.select_next_job([job("p3", priority="P3"), job("p2", priority="P2")]).selected_job_id, "p2")
    def test_55_risk_overrides_priority(self): self.assertEqual(queue.select_next_job([job("danger", priority="P0", risk_class=queue.PROHIBITED_UNATTENDED), job("safe", priority="P3")]).status, "QUEUE_BLOCKED")
    def test_56_window_open(self): self.assertIsNotNone(queue.select_next_job([job(deadline_class="TIME_WINDOW")], window_states={"job-a": "OPEN"}).selected_job_id)
    def test_57_window_closed(self): self.assertIsNone(queue.select_next_job([job(deadline_class="TIME_WINDOW")], window_states={"job-a": "CLOSED"}).selected_job_id)
    def test_58_window_expired(self): self.assertIsNone(queue.select_next_job([job(deadline_class="TIME_WINDOW")], window_states={"job-a": "EXPIRED"}).selected_job_id)
    def test_59_hard_deadline_open(self): self.assertIsNotNone(queue.select_next_job([job(deadline_class="HARD")], window_states={"job-a": "OPEN"}).selected_job_id)
    def test_60_hard_deadline_expired(self): self.assertIsNone(queue.select_next_job([job(deadline_class="HARD")], window_states={"job-a": "EXPIRED"}).selected_job_id)
    def test_61_cycle_two(self): self.assertIn("DEPENDENCY_CYCLE", queue.validate_queue([job("a", dependencies=("b",)), job("b", dependencies=("a",))])[1])
    def test_62_cycle_three(self): self.assertIn("DEPENDENCY_CYCLE", queue.validate_queue([job("a", dependencies=("b",)), job("b", dependencies=("c",)), job("c", dependencies=("a",))])[1])
    def test_63_duplicate_id(self): self.assertIn("DUPLICATE_JOB_ID", queue.validate_queue([job(), job()])[1])
    def test_64_unknown_dependency(self): self.assertIn("DEPENDENCY_UNKNOWN", queue.validate_queue([job(dependencies=("missing",))])[1])
    def test_65_malformed_dependency(self): self.assertIn("DEPENDENCY_INVALID", queue.validate_job(job(dependencies=["x"]))[1])
    def test_66_unknown_state(self): self.assertIn("JOB_STATE_UNKNOWN", queue.validate_job(job(state="UNKNOWN"))[1])
    def test_67_unknown_risk(self): self.assertIn("RISK_CLASS_UNKNOWN", queue.validate_job(job(risk_class="UNKNOWN"))[1])
    def test_68_unknown_version(self): self.assertIn("QUEUE_VERSION_UNSUPPORTED", queue.validate_job(job(queue_version="9"))[1])
    def test_69_unknown_retry(self): self.assertIn("RETRY_POLICY_UNKNOWN", queue.validate_job(job(retry_policy="UNKNOWN"))[1])
    def test_70_running_approval_contradiction(self): self.assertIn("APPROVAL_REQUIRED_WHILE_RUNNING", queue.validate_job(job(state=queue.RUNNING, requires_approval=True))[1])
    def test_71_prohibited_ready_contradiction(self): self.assertIn("PROHIBITED_JOB_READY", queue.validate_job(job(risk_class=queue.PROHIBITED_UNATTENDED))[1])
    def test_72_checkpoint_contradiction(self): self.assertIn("CHECKPOINT_FLAGS_CONTRADICTORY", queue.validate_job(job(state=queue.CHECKPOINTED, checkpoint_supported=False))[1])
    def test_73_event_allowlist(self): self.assertEqual(set(event().to_dict()), {"event_version", "event_type", "job_id", "job_type", "severity", "state", "approval_required", "summary_code", "occurred_at"})
    def test_74_event_secret_reject(self): self.assertIsNone(event(job_type="secret"))
    def test_75_event_url_reject(self): self.assertIsNone(event(job_id="https://example.invalid"))
    def test_76_event_path_reject(self): self.assertIsNone(event(job_type="C:/private"))
    def test_77_event_raw_exception_reject(self): self.assertIsNone(event(summary_code="RAW_EXCEPTION"))
    def test_78_switched_event(self): self.assertIsNotNone(event(event_type="JOB_SWITCHED", state=queue.READY, summary_code="SWITCH_TO_NEXT_JOB"))
    def test_79_waiting_event(self): self.assertIsNotNone(event(event_type="JOB_WAITING_APPROVAL", state=queue.WAITING_APPROVAL, approval_required=True, severity="WARN", summary_code="APPROVAL_REQUIRED"))
    def test_80_critical_event(self): self.assertIsNotNone(event(event_type="CRITICAL_STOP", state=queue.FAILED_SAFE, severity="CRITICAL", summary_code="QUEUE_FAIL_CLOSED"))
    def test_81_unknown_event_type(self): self.assertIsNone(event(event_type="UNKNOWN"))
    def test_82_event_extra_field(self): self.assertIsNone(queue.create_event(extra=True))
    def test_83_internal_exception_safe(self):
        with mock.patch.object(queue, "validate_queue", side_effect=RuntimeError("secret traceback")):
            result = queue.select_next_job([job()])
        self.assertEqual(result.reason_codes, ("INTERNAL_QUEUE_ERROR",)); self.assertNotIn("secret", repr(result.to_dict()))
    def test_84_reason_codes_deterministic(self): self.assertEqual(queue.validate_job(job(state="X", risk_class="Y"))[1], tuple(sorted(queue.validate_job(job(state="X", risk_class="Y"))[1])))
    def test_85_safe_decision_fields(self): self.assertEqual(set(queue.select_next_job([job()]).to_dict()), {"queue_version", "status", "selected_job_id", "action", "reason_codes"})


if __name__ == "__main__":
    unittest.main()
