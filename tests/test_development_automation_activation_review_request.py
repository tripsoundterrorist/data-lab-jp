from dataclasses import replace
from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import development_automation_activation_preflight as preflight  # noqa: E402
import development_automation_activation_review_request as review  # noqa: E402


NOW = 2_000_000_000
SHA = "b" * 40


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
        "activation-review-main",
        SHA,
        review.SCOPE,
        NOW,
        NOW + 300,
        False,
        False,
        False,
    )
    return replace(value, **changes)


class DevelopmentAutomationActivationReviewRequestTests(unittest.TestCase):
    def test_valid_request_is_ready_without_approval_or_activation(self):
        result = review.evaluate(
            preflight_evidence(),
            request(),
            expected_head_sha=SHA,
            evaluated_at_epoch_s=NOW + 1,
        )
        self.assertEqual(result.status, "REVIEW_REQUEST_READY")
        self.assertTrue(result.review_request_ready)
        self.assertFalse(result.approval_granted)
        self.assertFalse(result.activation_allowed)

    def test_preflight_must_be_ready(self):
        result = review.evaluate(
            preflight_evidence(fresh_usage_guard_required=False),
            request(),
            expected_head_sha=SHA,
            evaluated_at_epoch_s=NOW + 1,
        )
        self.assertEqual(result.status, "REVIEW_REQUEST_BLOCKED")
        self.assertIn("ACTIVATION_PREFLIGHT_NOT_READY", result.reason_codes)

    def test_identity_target_and_scope_are_exact(self):
        cases = (
            request(source="OTHER"),
            request(device_class="DESKTOP"),
            request(repository="other/repo"),
            request(base_branch="release"),
            request(request_id="../bad"),
            request(head_sha="c" * 39),
            request(scope="PRODUCTION_ACTIVATION"),
            request(request_version=object()),
        )
        for value in cases:
            with self.subTest(value=value):
                result = review.evaluate(
                    preflight_evidence(),
                    value,
                    expected_head_sha=SHA,
                    evaluated_at_epoch_s=NOW + 1,
                )
                self.assertEqual(result.status, "REVIEW_REQUEST_BLOCKED")

        result = review.evaluate(
            preflight_evidence(),
            request(),
            expected_head_sha="c" * 40,
            evaluated_at_epoch_s=NOW + 1,
        )
        self.assertEqual(result.status, "REVIEW_REQUEST_BLOCKED")
        self.assertIn("REVIEW_REQUEST_TARGET_MISMATCH", result.reason_codes)

        result = review.evaluate(
            preflight_evidence(),
            request(),
            expected_head_sha=None,
            evaluated_at_epoch_s=NOW + 1,
        )
        self.assertEqual(result.status, "REVIEW_REQUEST_BLOCKED")
        self.assertIn("REVIEW_REQUEST_TARGET_MISMATCH", result.reason_codes)

    def test_live_or_production_write_is_blocked(self):
        for value in (
            request(live_enabled=True),
            request(production_writes_enabled=True),
        ):
            with self.subTest(value=value):
                result = review.evaluate(
                    preflight_evidence(),
                    value,
                    expected_head_sha=SHA,
                    evaluated_at_epoch_s=NOW + 1,
                )
                self.assertEqual(result.status, "REVIEW_REQUEST_BLOCKED")
                self.assertFalse(result.activation_allowed)

    def test_additional_cost_requires_confirmation(self):
        result = review.evaluate(
            preflight_evidence(),
            request(additional_cost_required=True),
            expected_head_sha=SHA,
            evaluated_at_epoch_s=NOW + 1,
        )
        self.assertEqual(result.status, "COST_CONFIRMATION_REQUIRED")
        self.assertFalse(result.review_request_ready)

    def test_review_window_is_bounded_and_current(self):
        cases = (
            (request(requested_at_epoch_s=NOW + 2), NOW + 1),
            (request(expires_at_epoch_s=NOW), NOW),
            (request(expires_at_epoch_s=NOW + 300), NOW + 301),
            (
                request(
                    expires_at_epoch_s=(
                        NOW + review.MAX_REVIEW_WINDOW_SECONDS + 1
                    )
                ),
                NOW + 1,
            ),
        )
        for value, evaluated_at in cases:
            with self.subTest(value=value, evaluated_at=evaluated_at):
                result = review.evaluate(
                    preflight_evidence(),
                    value,
                    expected_head_sha=SHA,
                    evaluated_at_epoch_s=evaluated_at,
                )
                self.assertEqual(result.status, "REVIEW_REQUEST_BLOCKED")

    def test_bool_substitutes_and_wrong_types_are_rejected(self):
        for value in (request(live_enabled=0), request(additional_cost_required=None), {}):
            with self.subTest(value=value):
                result = review.evaluate(
                    preflight_evidence(),
                    value,
                    expected_head_sha=SHA,
                    evaluated_at_epoch_s=NOW + 1,
                )
                self.assertEqual(result.status, "REVIEW_REQUEST_BLOCKED")

    def test_no_io_clock_network_or_subprocess(self):
        with (
            mock.patch("builtins.open", side_effect=AssertionError),
            mock.patch("pathlib.Path.write_text", side_effect=AssertionError),
            mock.patch("time.time", side_effect=AssertionError),
            mock.patch("subprocess.run", side_effect=AssertionError),
        ):
            result = review.evaluate(
                preflight_evidence(),
                request(),
                expected_head_sha=SHA,
                evaluated_at_epoch_s=NOW + 1,
            )
        self.assertEqual(result.status, "REVIEW_REQUEST_READY")


if __name__ == "__main__":
    unittest.main()
