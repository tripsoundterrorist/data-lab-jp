from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import unattended_job_queue as queue  # noqa: E402
import unattended_runtime as runtime  # noqa: E402


def legacy(kind="JOB_COMPLETED", **changes):
    value = {
        "event_version": "0.1", "event_type": kind, "job_id": "job-a",
        "job_type": "static_validation", "severity": "INFO", "state": "DONE",
        "approval_required": False, "summary_code": "SAFE_EVENT",
        "occurred_at": "2026-08-31T14:00:00+09:00",
    }
    if kind == "JOB_WAITING_APPROVAL":
        value.update(severity="WARN", state="WAITING_APPROVAL",
                     approval_required=True)
    value.update(changes)
    return value


def queue_blocked(**changes):
    value = {
        "event_version": "0.2", "event_type": "QUEUE_BLOCKED",
        "subject_type": "QUEUE", "queue_id": queue.get_queue_identity().queue_id,
        "occurred_at": "2026-08-31T14:00:00+09:00", "severity": "ERROR",
        "state": "QUEUE_BLOCKED", "approval_required": False,
        "summary_code": "QUEUE_BLOCKED",
    }
    value.update(changes)
    return value


class NotificationIncidentIdentityTests(unittest.TestCase):
    def test_timestamp_changes_exact_but_not_incident_identity(self):
        first = legacy("JOB_WAITING_APPROVAL")
        later = dict(first, occurred_at="2026-08-31T14:20:00+09:00")
        self.assertNotEqual(runtime.event_identity(first), runtime.event_identity(later))
        self.assertEqual(runtime.incident_identity(first), runtime.incident_identity(later))

    def test_distinct_job_event_type_state_and_summary_are_distinct(self):
        base = legacy()
        values = (
            base,
            dict(base, job_id="job-b"),
            legacy("JOB_WAITING_APPROVAL"),
            dict(base, summary_code="OTHER_SAFE_EVENT"),
        )
        identities = {runtime.incident_identity(value) for value in values}
        self.assertEqual(len(identities), len(values))
        self.assertNotIn(None, identities)

    def test_v02_queue_timestamp_is_stable(self):
        first = queue_blocked()
        later = queue_blocked(occurred_at="2026-08-31T15:00:00+09:00")
        self.assertEqual(runtime.incident_identity(first), runtime.incident_identity(later))

    def test_typed_and_mapping_identity_match(self):
        mapping = queue_blocked()
        typed = queue.create_event(**mapping)
        self.assertIsNotNone(typed)
        self.assertEqual(runtime.incident_identity(mapping),
                         runtime.incident_identity(typed))

    def test_invalid_event_rejected_before_hashing(self):
        with mock.patch.object(runtime.hashlib, "sha256",
                               side_effect=AssertionError) as hash_fn:
            self.assertIsNone(runtime.incident_identity({}))
        hash_fn.assert_not_called()

    def test_input_is_not_mutated(self):
        value = legacy()
        before = deepcopy(value)
        runtime.incident_identity(value)
        self.assertEqual(value, before)

    def test_existing_exact_identity_is_unchanged(self):
        value = queue_blocked()
        before = runtime.event_identity(value)
        runtime.incident_identity(value)
        self.assertEqual(runtime.event_identity(value), before)

    def test_incident_identity_is_lowercase_sha256(self):
        identity = runtime.incident_identity(legacy())
        self.assertIsNotNone(identity)
        self.assertEqual(len(identity), 64)
        self.assertEqual(identity, identity.lower())
        int(identity, 16)

    def test_identity_performs_no_io(self):
        with (mock.patch("builtins.open", side_effect=AssertionError),
              mock.patch("pathlib.Path.write_text", side_effect=AssertionError)):
            self.assertIsNotNone(runtime.incident_identity(legacy()))


if __name__ == "__main__":
    unittest.main()
