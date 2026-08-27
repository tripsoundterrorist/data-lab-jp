"""Internal/test-only synthetic contracts. No execution, CLI or delivery API.

These fixtures do not represent real job transitions. Identity, classification,
messages and delivery remain exclusively owned by the existing Runtime pipeline.
"""


EXPANSION_VERSION = "0.1"
EVENT_TYPES = frozenset({"JOB_FAILED_SAFE", "QUEUE_BLOCKED", "JOB_COMPLETED"})


def fixture_event(event_type):
    """Return a fresh exact safe event; accept only the three validation cases."""
    if type(event_type) is not str or event_type not in EVENT_TYPES:
        raise ValueError("EXPANSION_EVENT_NOT_ALLOWED")
    severity, state = {
        "JOB_FAILED_SAFE": ("ERROR", "FAILED_SAFE"),
        "QUEUE_BLOCKED": ("WARN", "BLOCKED"),
        "JOB_COMPLETED": ("INFO", "DONE"),
    }[event_type]
    return {
        "event_version": "0.1", "event_type": event_type,
        "job_id": "notification-expansion-fixture-v0.1",
        "job_type": "notification_validation", "severity": severity,
        "state": state, "approval_required": False,
        "summary_code": "NOTIFICATION_EXPANSION_FIXTURE_V01",
        "occurred_at": "2026-08-27T00:00:00Z",
    }
