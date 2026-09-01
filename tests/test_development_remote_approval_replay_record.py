from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import development_remote_approval_replay_record as codec  # noqa: E402
import development_remote_iphone_approval_observation as approval  # noqa: E402
import development_gate_evidence as evidence_core  # noqa: E402


NOW = 2_000_000_000
SHA = "a" * 40


def observation(**changes):
    values = {
        "observation_version": approval.OBSERVATION_VERSION,
        "source": approval.APPROVED_SOURCE,
        "repository": approval.APPROVED_REPOSITORY,
        "device_class": approval.APPROVED_DEVICE_CLASS,
        "request_id": "approval-pr-49",
        "current_gate_id": "current-gate",
        "next_gate_id": "next-gate",
        "head_sha": SHA,
        "ci_run_id": 49,
        "status": "APPROVED",
        "requested_at_epoch_s": NOW - 60,
        "decided_at_epoch_s": NOW,
    }
    values.update(changes)
    return approval.RemoteApprovalObservation(**values)


def awaiting_approval():
    return evidence_core.DevelopmentGateEvidence(
        "current-gate", "next-gate", checkpoint_status="SAVED",
        checkpoint_ref="b" * 64, test_tier="REGRESSION",
        test_status="PASSED", commit_sha=SHA, pushed_sha=SHA,
        ci_status="SUCCESS", ci_head_sha=SHA, ci_run_id=49,
        approval_status="REQUIRED",
    )


def validated(value):
    return approval.observe(
        awaiting_approval(), value, evaluated_at_epoch_s=NOW
    )


def record(**changes):
    observed = observation()
    value = codec.build_record(observed, validated(observed))
    assert value is not None
    value.update(changes)
    return value


class DevelopmentRemoteApprovalReplayRecordTests(unittest.TestCase):
    def test_builder_emits_exact_sanitized_schema(self):
        value = record()
        self.assertEqual(set(value), codec.RECORD_FIELDS)
        self.assertEqual(value["record_version"], codec.RECORD_VERSION)
        self.assertNotIn("requested_at_epoch_s", value)

    def test_only_approved_observation_builds_record(self):
        pending = observation(status="PENDING", decided_at_epoch_s=None)
        denied = observation(status="DENIED")
        stale = observation(
            requested_at_epoch_s=NOW - 400, decided_at_epoch_s=NOW - 301,
        )
        mismatched = observation(ci_run_id=50)
        cases = (
            (object(), object()),
            (observation(), object()),
            (pending, validated(pending)),
            (denied, validated(denied)),
            (stale, validated(stale)),
            (mismatched, validated(mismatched)),
        )
        for value, result in cases:
            with self.subTest(value=value, result=result):
                self.assertIsNone(codec.build_record(value, result))

    def test_exact_record_is_valid(self):
        self.assertTrue(codec.validate_record(record()))

    def test_invalid_records_fail_closed(self):
        cases = (
            {},
            record(extra=True),
            record(record_version="9.9"),
            record(source="CHAT_MESSAGE"),
            record(repository="other/repo"),
            record(device_class="IPAD"),
            record(request_id="invalid request"),
            record(current_gate_id="next-gate"),
            record(head_sha="a" * 39),
            record(ci_run_id=0),
            record(decision_status="DENIED"),
            record(decided_at_epoch_s=-1),
        )
        for value in cases:
            with self.subTest(value=value):
                self.assertFalse(codec.validate_record(value))
                self.assertEqual(
                    codec.validate_snapshot([value]).status,
                    "SNAPSHOT_INVALID",
                )

    def test_empty_and_distinct_snapshots_are_valid(self):
        second = record(
            request_id="approval-pr-50", next_gate_id="later-gate",
            head_sha="b" * 40, ci_run_id=50,
        )
        self.assertEqual(codec.validate_snapshot([]).record_count, 0)
        result = codec.validate_snapshot([record(), second])
        self.assertEqual((result.status, result.record_count),
                         ("SNAPSHOT_VALID", 2))

    def test_duplicate_request_id_blocks_snapshot(self):
        duplicate = record(
            next_gate_id="later-gate", head_sha="b" * 40, ci_run_id=50,
        )
        result = codec.validate_snapshot([record(), duplicate])
        self.assertEqual(
            result.reason_codes,
            ("REMOTE_APPROVAL_REQUEST_ID_DUPLICATE",),
        )

    def test_duplicate_target_blocks_snapshot(self):
        duplicate = record(request_id="approval-pr-50")
        result = codec.validate_snapshot([record(), duplicate])
        self.assertEqual(
            result.reason_codes,
            ("REMOTE_APPROVAL_TARGET_DUPLICATE",),
        )

    def test_consumed_request_is_detected(self):
        result = codec.find_consumed_request([record()], "approval-pr-49")
        self.assertEqual(result.status, "APPROVAL_ALREADY_CONSUMED")
        self.assertTrue(result.consumed)
        self.assertEqual(
            result.reason_codes, ("REMOTE_APPROVAL_REPLAY_DETECTED",)
        )

    def test_fresh_request_is_not_inferred_as_consumed(self):
        result = codec.find_consumed_request([record()], "approval-pr-50")
        self.assertEqual(result.status, "APPROVAL_NOT_CONSUMED")
        self.assertFalse(result.consumed)

    def test_invalid_lookup_or_snapshot_blocks(self):
        self.assertEqual(
            codec.find_consumed_request([], "invalid request").status,
            "EVIDENCE_INVALID",
        )
        self.assertEqual(
            codec.find_consumed_request({}, "approval-pr-49").status,
            "EVIDENCE_BLOCKED",
        )

    def test_inputs_are_not_mutated_and_codec_performs_no_io(self):
        records = [record()]
        before = deepcopy(records)
        with (mock.patch("builtins.open", side_effect=AssertionError),
              mock.patch("pathlib.Path.write_text", side_effect=AssertionError)):
            codec.validate_snapshot(records)
            codec.find_consumed_request(records, "approval-pr-49")
        self.assertEqual(records, before)


if __name__ == "__main__":
    unittest.main()
