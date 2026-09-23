from dataclasses import asdict
import copy
import inspect
import json
import pickle
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import affiliate_cta_network_disabled_wire_adapter as adapter
import affiliate_cta_offline_synthetic_fixture_integration as subject
import affiliate_cta_offline_provider_factory as factory
import affiliate_cta_production_composition as composition
import affiliate_cta_approved_context as approved
from datetime import datetime, timezone


CONTENT = "fixture-content_01"
TARGET = "https://al.fanza.co.jp/?lurl=https%3A%2F%2Fexample.invalid%2F"
NOW = datetime(2026, 9, 23, tzinfo=timezone.utc)
PUBLIC_IDS = tuple(f"itm_{number:024x}" for number in range(10))


def fixture():
    return {"result": {
        "status": 200, "result_count": 1, "total_count": 1,
        "first_position": 1,
        "items": [{"content_id": CONTENT, "affiliateURL": TARGET}],
    }}


def provider():
    context = approved._make_test_context(PUBLIC_IDS, lambda _value: None)
    mapping = {value: f"other-{index}" for index, value in enumerate(PUBLIC_IDS)}
    mapping[PUBLIC_IDS[0]] = CONTENT
    return factory._build_offline_provider_for_test(context, mapping, lambda _value: None, lambda: NOW)


class OfflineSyntheticFixtureIntegrationTests(unittest.TestCase):
    def test_one_adapter_validation_reaches_opaque_harness_idempotently(self):
        offline_provider = provider()
        with mock.patch.object(
            adapter, "validate_synthetic_fixture_for_offline_harness",
            wraps=adapter.validate_synthetic_fixture_for_offline_harness,
        ) as validated:
            first = subject._run_synthetic_fixture_integration_for_test(
                payload=fixture(), requested_content_id=CONTENT, provider=offline_provider, public_id=PUBLIC_IDS[0],
            )
            second = subject._run_synthetic_fixture_integration_for_test(
                payload=fixture(), requested_content_id=CONTENT, provider=offline_provider, public_id=PUBLIC_IDS[0],
            )
        self.assertEqual(validated.call_count, 2)
        self.assertEqual(first, second)
        self.assertEqual(first.status, subject.ACCEPTED)
        self.assertTrue(first.adapter_validated)
        self.assertTrue(first.harness_accepted)
        self.assertFalse(first.production_activation_allowed)
        self.assertFalse(first.serialization_allowed)

    def test_rejection_and_adapter_exception_are_fixed_fail_closed(self):
        offline_provider = provider()
        rejected = subject._run_synthetic_fixture_integration_for_test(
            payload={"result": {}}, requested_content_id=CONTENT, provider=offline_provider, public_id=PUBLIC_IDS[0],
        )
        self.assertEqual((rejected.status, rejected.adapter_validated, rejected.harness_accepted), (
            subject.REJECTED, False, False,
        ))
        with mock.patch.object(
            adapter, "validate_synthetic_fixture_for_offline_harness", side_effect=RuntimeError("marker"),
        ):
            failed = subject._run_synthetic_fixture_integration_for_test(
                payload=fixture(), requested_content_id=CONTENT, provider=offline_provider, public_id=PUBLIC_IDS[0],
            )
        self.assertEqual((failed.status, failed.adapter_validated, failed.harness_accepted), (
            subject.FAIL_CLOSED, False, False,
        ))
        self.assertNotIn("marker", repr(failed))

    def test_real_offline_provider_receives_same_object_once_and_blocks_replay(self):
        offline_provider = provider()
        observation = adapter.validate_synthetic_fixture_for_offline_harness(fixture(), CONTENT)
        with mock.patch.object(
            factory._OfflineProvider, "_consume_validated_synthetic_observation_for_test",
            wraps=offline_provider._consume_validated_synthetic_observation_for_test,
        ) as consumed:
            first = offline_provider._consume_validated_synthetic_observation_for_test(PUBLIC_IDS[0], observation)
        self.assertIsNotNone(first)
        self.assertIs(consumed.call_args.args[1], observation)
        self.assertIsNone(offline_provider._consume_validated_synthetic_observation_for_test(PUBLIC_IDS[0], observation))
        forged = object.__new__(adapter.ValidatedSyntheticFixtureObservation)
        self.assertIsNone(offline_provider._consume_validated_synthetic_observation_for_test(PUBLIC_IDS[0], forged))

    def test_end_to_end_invokes_adapter_once_and_passes_its_exact_object(self):
        offline_provider = provider()
        issued, received = [], []
        original_validate = adapter.validate_synthetic_fixture_for_offline_harness
        original_consume = offline_provider._consume_validated_synthetic_observation_for_test

        def validate_once(payload, requested_content_id):
            result = original_validate(payload, requested_content_id)
            issued.append(result)
            return result

        def consume_once(public_id, observation):
            received.append(observation)
            return original_consume(public_id, observation)

        with mock.patch.object(adapter, "validate_synthetic_fixture_for_offline_harness", side_effect=validate_once) as validated, \
             mock.patch.object(factory._OfflineProvider, "_consume_validated_synthetic_observation_for_test", side_effect=consume_once) as consumed:
            receipt = subject._run_synthetic_fixture_integration_for_test(
                payload=fixture(), requested_content_id=CONTENT, provider=offline_provider, public_id=PUBLIC_IDS[0],
            )
        self.assertEqual(receipt.status, subject.ACCEPTED)
        self.assertEqual(validated.call_count, 1)
        self.assertEqual(consumed.call_count, 1)
        self.assertEqual(len(issued), 1)
        self.assertEqual(len(received), 1)
        self.assertIs(received[0], issued[0])

    def test_consumer_rejection_or_exception_is_fixed_failure(self):
        offline_provider = provider()
        for replacement in (None, RuntimeError("marker")):
            with self.subTest(replacement_type=type(replacement)):
                with mock.patch.object(
                    factory._OfflineProvider, "_consume_validated_synthetic_observation_for_test",
                    side_effect=replacement if isinstance(replacement, Exception) else None,
                    return_value=replacement if replacement is None else mock.DEFAULT,
                ):
                    receipt = subject._run_synthetic_fixture_integration_for_test(
                        payload=fixture(), requested_content_id=CONTENT,
                        provider=offline_provider, public_id=PUBLIC_IDS[0],
                    )
                self.assertEqual((receipt.status, receipt.adapter_validated, receipt.harness_accepted), (
                    subject.FAIL_CLOSED, True, False,
                ))

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

    def test_pickle_copy_and_state_exports_are_forbidden_without_values(self):
        for operation in (
            lambda value: value.__reduce__(), lambda value: value.__reduce_ex__(0),
            lambda value: value.__getstate__(), lambda value: value.__setstate__({}),
            copy.copy, copy.deepcopy,
        ):
            with self.subTest(operation=operation):
                with self.assertRaisesRegex(TypeError, "SYNTHETIC_OBSERVATION_EXPORT_FORBIDDEN") as error:
                    operation(adapter.validate_synthetic_fixture_for_offline_harness(fixture(), CONTENT))
                self.assertNotIn(CONTENT, str(error.exception))
                self.assertNotIn(TARGET, str(error.exception))
        for protocol in range(pickle.HIGHEST_PROTOCOL + 1):
            with self.subTest(protocol=protocol):
                with self.assertRaisesRegex(TypeError, "SYNTHETIC_OBSERVATION_EXPORT_FORBIDDEN") as error:
                    pickle.dumps(adapter.validate_synthetic_fixture_for_offline_harness(fixture(), CONTENT), protocol)
                self.assertNotIn(CONTENT, str(error.exception))
                self.assertNotIn(TARGET, str(error.exception))

    def test_malicious_special_methods_never_escape_the_integration_receipt(self):
        class Explodes:
            def __getattribute__(self, _name):
                raise RuntimeError("private-marker")
            def __repr__(self):
                return "private-marker"
        receipt = subject._run_synthetic_fixture_integration_for_test(
            payload={"result": Explodes()}, requested_content_id=CONTENT,
            provider=provider(), public_id=PUBLIC_IDS[0],
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
