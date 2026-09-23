from dataclasses import asdict, replace
from datetime import datetime, timezone
import inspect
import json
from pathlib import Path
import pickle
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import affiliate_cta_approved_context as approved
import affiliate_cta_network_disabled_wire_adapter as adapter
import affiliate_cta_offline_provider_factory as factory
import affiliate_cta_offline_wire_projection_redaction as subject
import affiliate_cta_preconnection_synthetic_envelope as preconnection
import affiliate_cta_production_composition as composition


CONTENT = "fixture-content_01"
TARGET = "https://al.fanza.co.jp/?lurl=https%3A%2F%2Fexample.invalid%2F"
NOW = datetime(2026, 9, 23, tzinfo=timezone.utc)
PUBLIC_IDS = tuple(f"itm_{number:024x}" for number in range(10))


def payload():
    return {"result": {
        "status": 200, "result_count": 1, "total_count": 1, "first_position": 1,
        "items": [{"content_id": CONTENT, "affiliateURL": TARGET}],
    }}


def provider():
    context = approved._make_test_context(PUBLIC_IDS, lambda _value: None)
    mapping = {value: f"other-{index}" for index, value in enumerate(PUBLIC_IDS)}
    mapping[PUBLIC_IDS[0]] = CONTENT
    return factory._build_offline_provider_for_test(context, mapping, lambda _value: None, lambda: NOW)


class TestOfflineWireProjectionRedaction(unittest.TestCase):
    def assess(self, value, *, dispositions=None, offline_provider=None):
        return subject._run_offline_projection_for_test(
            dispositions=subject.fixed_field_dispositions_for_test() if dispositions is None else dispositions,
            payload=value, requested_content_id=CONTENT,
            provider=provider() if offline_provider is None else offline_provider,
            public_id=PUBLIC_IDS[0],
        )

    def test_normal_projection_calls_existing_seams_once(self):
        owner = provider()
        issued, received = [], []
        original_validate = adapter.validate_synthetic_fixture_for_offline_harness
        original_consume = factory._consume_validated_synthetic_for_test

        def validate_once(value, requested):
            result = original_validate(value, requested)
            issued.append(result)
            return result

        def consume_once(value, public_id, observation):
            received.append(observation)
            return original_consume(value, public_id, observation)

        with mock.patch.object(adapter, "validate_synthetic_fixture_for_offline_harness", side_effect=validate_once) as semantic, \
             mock.patch.object(factory, "_consume_validated_synthetic_for_test", side_effect=consume_once) as consumer:
            receipt = self.assess(payload(), offline_provider=owner)
        self.assertEqual(receipt.status, subject.ACCEPTED)
        self.assertEqual((semantic.call_count, consumer.call_count), (1, 1))
        self.assertIs(received[0], issued[0])
        self.assertEqual(receipt.kept_field_count, 8)
        self.assertTrue(receipt.adapter_validated); self.assertTrue(receipt.owner_consumed)
        self.assertFalse(receipt.connection_allowed); self.assertFalse(receipt.compatibility_verified)

    def test_request_echo_is_never_read_or_exported(self):
        events = []
        class Hostile:
            def __eq__(self, _other): events.append("eq"); return False
            def __hash__(self): events.append("hash"); return 1
            def __iter__(self): events.append("iter"); return iter(())
            def __repr__(self): events.append("repr"); return "secret-like-marker"
            def __str__(self): events.append("str"); return "secret-like-marker"
            def __bool__(self): events.append("bool"); return True
            def __getitem__(self, _key): events.append("getitem"); return None
        value = payload(); value["request"] = Hostile()
        with mock.patch.object(adapter, "validate_synthetic_fixture_for_offline_harness") as semantic, \
             mock.patch.object(factory, "_consume_validated_synthetic_for_test") as consumer:
            receipt = self.assess(value)
        self.assertEqual(receipt.reason_code, "REQUEST_ECHO_DROPPED")
        self.assertTrue(receipt.request_echo_dropped)
        self.assertEqual((semantic.call_count, consumer.call_count), (0, 0))
        self.assertEqual(events, [])
        for rendered in (repr(receipt), json.dumps(asdict(receipt)), pickle.dumps(receipt)):
            self.assertNotIn(b"secret-like-marker" if type(rendered) is bytes else "secret-like-marker", rendered)

    def test_unknown_extra_and_wrong_shape_block_without_silent_strip(self):
        root_extra = {**payload(), "unknown": 1}
        result_extra = {"result": {**payload()["result"], "unknown": 1}}
        item_extra = payload(); item_extra["result"]["items"][0]["unknown"] = 1
        duplicate_item = payload(); duplicate_item["result"]["items"].append(dict(duplicate_item["result"]["items"][0]))
        cases = (root_extra, result_extra, item_extra, duplicate_item, {}, {"result": {}},
                 {"result": {**payload()["result"], "items": []}},
                 {"result": {**payload()["result"], "items": [dict(payload()["result"]["items"][0])], "status": "200"}})
        for value in cases:
            with self.subTest(case=type(value)):
                with mock.patch.object(adapter, "validate_synthetic_fixture_for_offline_harness", wraps=adapter.validate_synthetic_fixture_for_offline_harness) as semantic:
                    receipt = self.assess(value)
                self.assertNotEqual(receipt.status, subject.ACCEPTED)
                self.assertLessEqual(semantic.call_count, 1)

    def test_kept_semantic_malformed_field_reaches_adapter_once(self):
        value = payload(); value["result"]["status"] = "200"
        with mock.patch.object(adapter, "validate_synthetic_fixture_for_offline_harness", wraps=adapter.validate_synthetic_fixture_for_offline_harness) as semantic, \
             mock.patch.object(factory, "_consume_validated_synthetic_for_test") as consumer:
            receipt = self.assess(value)
        self.assertEqual(receipt.reason_code, "SEMANTIC_VALIDATION_BLOCKED")
        self.assertEqual((semantic.call_count, consumer.call_count), (1, 0))

    def test_disposition_evidence_rejects_hostile_or_unresolved_before_semantics(self):
        base = subject.fixed_field_dispositions_for_test()
        class Hostile:
            def __eq__(self, _other): raise RuntimeError("marker")
            def __hash__(self): raise RuntimeError("marker")
            def __repr__(self): return "marker"
        class StringSubclass(str):
            pass
        cases = [(), base + (base[0],), tuple(item for item in base if item.field_path != "request"),
                 tuple(replace(item, superseded=True) if item.field_path == "request" else item for item in base),
                 tuple(replace(item, field_path="unknown") if item.field_path == "request" else item for item in base),
                 tuple(replace(item, disposition=subject.UNCONFIRMED) if item.field_path == "result" else item for item in base)]
        for field in ("field_path", "disposition", "classification", "source_reference", "source_digest", "source_checked_at", "scope", "reason"):
            cases.append(tuple(replace(item, **{field: Hostile()}) if item.field_path == "result" else item for item in base))
            cases.append(tuple(replace(item, **{field: StringSubclass(getattr(item, field))}) if item.field_path == "result" else item for item in base))
        with mock.patch.object(adapter, "validate_synthetic_fixture_for_offline_harness") as semantic, \
             mock.patch.object(factory, "_consume_validated_synthetic_for_test") as consumer:
            for dispositions in cases:
                with self.subTest(size=len(dispositions)):
                    self.assertEqual(self.assess(payload(), dispositions=dispositions).reason_code, "DISPOSITION_EVIDENCE_BLOCKED")
        self.assertEqual((semantic.call_count, consumer.call_count), (0, 0))

    def test_exceptions_are_value_free_and_defaults_stay_disabled(self):
        with mock.patch.object(adapter, "validate_synthetic_fixture_for_offline_harness", side_effect=RuntimeError("secret-like-marker")):
            receipt = self.assess(payload())
        self.assertEqual(receipt.reason_code, "INTERNAL_FAILURE")
        self.assertNotIn("secret-like-marker", repr(receipt))
        self.assertIsNone(subject.production_projection())
        self.assertIsNone(adapter.production_adapter())
        self.assertIsNone(composition.production_provider())
        self.assertIsNone(subject.OFFICIAL_WIRE_CONTRACT_VERSION)
        source = inspect.getsource(subject)
        self.assertNotIn("_parse_fixture_for_test", source)
        self.assertNotIn("_content_id_valid", source)
        self.assertIn("validate_synthetic_fixture_for_offline_harness", source)
        self.assertIsNone(preconnection.production_policy())


if __name__ == "__main__":
    unittest.main()
