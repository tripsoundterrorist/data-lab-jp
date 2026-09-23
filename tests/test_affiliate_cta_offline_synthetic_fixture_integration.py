from dataclasses import asdict
import inspect
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import affiliate_cta_network_disabled_wire_adapter as adapter
import affiliate_cta_offline_synthetic_fixture_integration as subject
import affiliate_cta_production_composition as composition


CONTENT = "fixture-content_01"
TARGET = "https://al.fanza.co.jp/?lurl=https%3A%2F%2Fexample.invalid%2F"


def fixture():
    return {"result": {
        "status": 200, "result_count": 1, "total_count": 1,
        "first_position": 1,
        "items": [{"content_id": CONTENT, "affiliateURL": TARGET}],
    }}


class OfflineSyntheticFixtureIntegrationTests(unittest.TestCase):
    def test_one_adapter_validation_reaches_opaque_harness_idempotently(self):
        with mock.patch.object(
            adapter, "validate_synthetic_fixture_for_offline_harness",
            wraps=adapter.validate_synthetic_fixture_for_offline_harness,
        ) as validated:
            first = subject._run_synthetic_fixture_integration_for_test(
                payload=fixture(), requested_content_id=CONTENT,
            )
            second = subject._run_synthetic_fixture_integration_for_test(
                payload=fixture(), requested_content_id=CONTENT,
            )
        self.assertEqual(validated.call_count, 2)
        self.assertEqual(first, second)
        self.assertEqual(first.status, subject.ACCEPTED)
        self.assertTrue(first.adapter_validated)
        self.assertTrue(first.harness_accepted)
        self.assertFalse(first.production_activation_allowed)
        self.assertFalse(first.serialization_allowed)

    def test_rejection_and_adapter_exception_are_fixed_fail_closed(self):
        rejected = subject._run_synthetic_fixture_integration_for_test(
            payload={"result": {}}, requested_content_id=CONTENT,
        )
        self.assertEqual((rejected.status, rejected.adapter_validated, rejected.harness_accepted), (
            subject.REJECTED, False, False,
        ))
        with mock.patch.object(
            adapter, "validate_synthetic_fixture_for_offline_harness", side_effect=RuntimeError("marker"),
        ):
            failed = subject._run_synthetic_fixture_integration_for_test(
                payload=fixture(), requested_content_id=CONTENT,
            )
        self.assertEqual((failed.status, failed.adapter_validated, failed.harness_accepted), (
            subject.FAIL_CLOSED, False, False,
        ))
        self.assertNotIn("marker", repr(failed))

    def test_observation_is_opaque_and_not_serializable(self):
        observation = adapter.validate_synthetic_fixture_for_offline_harness(fixture(), CONTENT)
        self.assertIs(type(observation), adapter.ValidatedSyntheticFixtureObservation)
        self.assertNotIn(CONTENT, repr(observation))
        self.assertNotIn(TARGET, repr(observation))
        self.assertFalse(hasattr(observation, "to_dict"))
        with self.assertRaises(TypeError):
            adapter.ValidatedSyntheticFixtureObservation(CONTENT, TARGET)
        with self.assertRaises(TypeError):
            vars(observation)
        with self.assertRaises(TypeError):
            asdict(observation)
        with self.assertRaises(TypeError):
            json.dumps(observation)

    def test_malicious_special_methods_never_escape_the_integration_receipt(self):
        class Explodes:
            def __getattribute__(self, _name):
                raise RuntimeError("private-marker")
            def __repr__(self):
                return "private-marker"
        receipt = subject._run_synthetic_fixture_integration_for_test(
            payload={"result": Explodes()}, requested_content_id=CONTENT,
        )
        self.assertEqual(receipt.status, subject.REJECTED)
        self.assertNotIn("private-marker", repr(receipt))

    def test_integration_does_not_reuse_adapter_private_validators(self):
        source = inspect.getsource(subject)
        self.assertNotIn("_parse_fixture_for_test", source)
        self.assertNotIn("_content_id_valid", source)
        self.assertNotIn("_keys_exact", source)
        self.assertIn("validate_synthetic_fixture_for_offline_harness", source)

    def test_no_production_or_public_entrypoint_injection(self):
        self.assertIsNone(subject.production_integration())
        self.assertIsNone(adapter.production_adapter())
        self.assertIsNone(composition.production_provider())
        self.assertEqual(tuple(inspect.signature(subject.production_integration).parameters), ())


if __name__ == "__main__":
    unittest.main()
