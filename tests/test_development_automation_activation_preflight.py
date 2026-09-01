from dataclasses import replace
from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import development_automation_activation_preflight as preflight  # noqa: E402


def evidence(**changes):
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


class DevelopmentAutomationActivationPreflightTests(unittest.TestCase):
    def test_complete_evidence_requires_manual_review_without_activation(self):
        result = preflight.evaluate(evidence())
        self.assertEqual(result.status, "PREFLIGHT_READY_FOR_MANUAL_REVIEW")
        self.assertFalse(result.activation_allowed)
        self.assertTrue(result.manual_activation_review_required)
        self.assertIn("PRODUCTION_ACTIVATION_NOT_IMPLEMENTED", result.reason_codes)

    def test_live_or_production_write_enabled_is_blocked(self):
        for value in (
            evidence(live_enabled=True),
            evidence(production_writes_enabled=True),
        ):
            with self.subTest(value=value):
                result = preflight.evaluate(value)
                self.assertEqual(result.status, "PREFLIGHT_BLOCKED")
                self.assertFalse(result.activation_allowed)

    def test_additional_cost_stops_for_confirmation(self):
        result = preflight.evaluate(evidence(additional_cost_required=True))
        self.assertEqual(result.status, "COST_CONFIRMATION_REQUIRED")
        self.assertFalse(result.activation_allowed)
        self.assertIn(
            "ADDITIONAL_COST_REQUIRES_CONFIRMATION", result.reason_codes
        )

    def test_each_required_protection_fails_closed_when_missing(self):
        fields = (
            "observation_chain_verified",
            "fresh_usage_guard_required",
            "blocked_checkpoint_required",
            "blocked_safe_task_switch_required",
            "operational_reserve_required",
            "explicit_merge_approval_required",
        )
        for field in fields:
            with self.subTest(field=field):
                result = preflight.evaluate(evidence(**{field: False}))
                self.assertEqual(result.status, "PREFLIGHT_BLOCKED")
                self.assertFalse(result.activation_allowed)

    def test_action_order_and_identity_are_exact(self):
        cases = (
            evidence(repository="other/repo"),
            evidence(base_branch="release"),
            evidence(configured_actions=tuple(reversed(preflight.REQUIRED_ACTIONS))),
            evidence(configured_actions=preflight.REQUIRED_ACTIONS[:-1]),
        )
        for value in cases:
            with self.subTest(value=value):
                self.assertEqual(
                    preflight.evaluate(value).status, "PREFLIGHT_BLOCKED"
                )

    def test_bool_substitutes_and_wrong_types_are_rejected(self):
        cases = (
            evidence(live_enabled=0),
            evidence(additional_cost_required=None),
            replace(evidence(), configured_actions=list(preflight.REQUIRED_ACTIONS)),
            {},
        )
        for value in cases:
            with self.subTest(value=value):
                self.assertEqual(
                    preflight.evaluate(value).status, "PREFLIGHT_BLOCKED"
                )

    def test_no_io_clock_network_or_subprocess(self):
        with (
            mock.patch("builtins.open", side_effect=AssertionError),
            mock.patch("pathlib.Path.write_text", side_effect=AssertionError),
            mock.patch("time.time", side_effect=AssertionError),
            mock.patch("subprocess.run", side_effect=AssertionError),
        ):
            result = preflight.evaluate(evidence())
        self.assertEqual(result.status, "PREFLIGHT_READY_FOR_MANUAL_REVIEW")


if __name__ == "__main__":
    unittest.main()
