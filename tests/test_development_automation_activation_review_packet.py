from dataclasses import replace
from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import development_automation_activation_preflight as preflight  # noqa: E402
import development_automation_activation_review_packet as packet  # noqa: E402
import development_automation_activation_review_request as review  # noqa: E402


NOW = 2_000_000_000
SHA = "d" * 40


def preflight_evidence(**changes):
    value = preflight.ActivationPreflightEvidence(
        preflight.PREFLIGHT_VERSION,
        preflight.APPROVED_REPOSITORY,
        preflight.APPROVED_BASE,
        preflight.REQUIRED_ACTIONS,
        True,
        True,
        True,
        True,
        True,
        True,
        False,
        False,
        False,
    )
    return replace(value, **changes)


def request(**changes):
    value = review.ActivationReviewRequest(
        review.REQUEST_VERSION,
        review.SOURCE,
        review.DEVICE_CLASS,
        preflight.APPROVED_REPOSITORY,
        preflight.APPROVED_BASE,
        "activation-review-packet",
        SHA,
        review.SCOPE,
        NOW,
        NOW + 300,
        False,
        False,
        False,
    )
    return replace(value, **changes)


def build(value=None, **changes):
    return packet.build(
        preflight_evidence(),
        request() if value is None else value,
        expected_head_sha=SHA,
        evaluated_at_epoch_s=NOW + 1,
        **changes,
    )


class DevelopmentAutomationActivationReviewPacketTests(unittest.TestCase):
    def test_valid_request_builds_minimal_review_only_packet(self):
        actual = build()
        self.assertEqual(actual.status, "REVIEW_PACKET_READY")
        self.assertTrue(actual.manual_review_ready)
        self.assertEqual(actual.repository, preflight.APPROVED_REPOSITORY)
        self.assertEqual(actual.base_branch, preflight.APPROVED_BASE)
        self.assertEqual(actual.head_sha, SHA)
        self.assertEqual(actual.head_sha_short, SHA[:12])
        self.assertEqual(actual.request_id, "activation-review-packet")
        self.assertEqual(actual.review_window_seconds, 300)
        self.assertFalse(actual.approval_granted)
        self.assertFalse(actual.activation_allowed)

    def test_target_mismatch_is_blocked_without_echo(self):
        actual = packet.build(
            preflight_evidence(),
            request(),
            expected_head_sha="e" * 40,
            evaluated_at_epoch_s=NOW + 1,
        )
        self.assertEqual(actual.status, "REVIEW_PACKET_BLOCKED")
        self.assertIn("REVIEW_REQUEST_TARGET_MISMATCH", actual.reason_codes)
        self.assertEqual(actual.head_sha, "")
        self.assertEqual(actual.request_id, "")

    def test_invalid_identity_is_blocked_without_echo(self):
        actual = build(request(request_id="secret value"))
        self.assertEqual(actual.status, "REVIEW_PACKET_BLOCKED")
        self.assertEqual(actual.repository, "")
        self.assertEqual(actual.request_id, "")
        self.assertEqual(actual.review_window_seconds, 0)

    def test_preflight_failure_is_blocked(self):
        actual = packet.build(
            preflight_evidence(observation_chain_verified=False),
            request(),
            expected_head_sha=SHA,
            evaluated_at_epoch_s=NOW + 1,
        )
        self.assertEqual(actual.status, "REVIEW_PACKET_BLOCKED")
        self.assertIn("ACTIVATION_PREFLIGHT_NOT_READY", actual.reason_codes)

    def test_live_writes_and_cost_never_reach_ready_packet(self):
        for value in (
            request(live_enabled=True),
            request(production_writes_enabled=True),
            request(additional_cost_required=True),
        ):
            with self.subTest(value=value):
                actual = build(value)
                self.assertEqual(actual.status, "REVIEW_PACKET_BLOCKED")
                self.assertFalse(actual.live_enabled)
                self.assertFalse(actual.production_writes_enabled)
                self.assertFalse(actual.additional_cost_required)
                self.assertFalse(actual.approval_granted)
                self.assertFalse(actual.activation_allowed)

    def test_expired_or_oversized_window_is_blocked(self):
        for value, evaluated_at in (
            (request(expires_at_epoch_s=NOW + 300), NOW + 301),
            (
                request(
                    expires_at_epoch_s=(
                        NOW + review.MAX_REVIEW_WINDOW_SECONDS + 1
                    )
                ),
                NOW + 1,
            ),
        ):
            with self.subTest(value=value):
                actual = packet.build(
                    preflight_evidence(),
                    value,
                    expected_head_sha=SHA,
                    evaluated_at_epoch_s=evaluated_at,
                )
                self.assertEqual(actual.status, "REVIEW_PACKET_BLOCKED")

    def test_wrong_types_are_fail_closed(self):
        for value, expected_sha, evaluated_at in (
            ({}, SHA, NOW + 1),
            (request(), None, NOW + 1),
            (request(), SHA, True),
        ):
            with self.subTest(value=value):
                actual = packet.build(
                    preflight_evidence(),
                    value,
                    expected_head_sha=expected_sha,
                    evaluated_at_epoch_s=evaluated_at,
                )
                self.assertEqual(actual.status, "REVIEW_PACKET_BLOCKED")

    def test_builder_has_no_io_clock_network_or_subprocess(self):
        with (
            mock.patch("builtins.open", side_effect=AssertionError),
            mock.patch("pathlib.Path.write_text", side_effect=AssertionError),
            mock.patch("time.time", side_effect=AssertionError),
            mock.patch("subprocess.run", side_effect=AssertionError),
        ):
            actual = build()
        self.assertEqual(actual.status, "REVIEW_PACKET_READY")


if __name__ == "__main__":
    unittest.main()
