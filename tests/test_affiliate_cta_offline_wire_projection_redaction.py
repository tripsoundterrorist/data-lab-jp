from dataclasses import asdict, replace
from datetime import datetime, timezone
import inspect
import json
from pathlib import Path
import pickle
import copy
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
    def assess(self, value, *, dispositions=None, offline_provider=None, envelope_changes=None):
        raw = value if type(value) is bytes else json.dumps(value, separators=(",", ":")).encode("utf-8")
        inputs = dict(status=200, media_type="application/json", body=raw,
                      elapsed_ms=1, budget_ms=2)
        inputs.update(envelope_changes or {})
        envelope = preconnection._synthetic_envelope_for_test(**inputs)
        return subject.run_composed_synthetic_projection_for_test(
            evidence=preconnection.fixed_evidence_for_test(), envelope=envelope,
            dispositions=subject.fixed_field_dispositions_for_test() if dispositions is None else dispositions,
            requested_content_id=CONTENT,
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
            projected, reason, echo = subject._project_minimum_subset(value)
        self.assertIsNone(projected)
        self.assertEqual(reason, "REQUEST_ECHO_DROPPED")
        self.assertTrue(echo)
        self.assertEqual((semantic.call_count, consumer.call_count), (0, 0))
        self.assertEqual(events, [])
        receipt = self.assess({**payload(), "request": "dummy"})
        self.assertEqual(receipt.reason_code, "REQUEST_ECHO_DROPPED")
        self.assertTrue(receipt.request_echo_dropped)
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

    def test_root_keys_are_type_checked_before_any_membership_hook(self):
        events = []
        class Colliding:
            def __hash__(self): events.append("hash"); return hash("request")
            def __eq__(self, _other): events.append("eq"); raise RuntimeError("marker")
            def __repr__(self): events.append("repr"); return "marker"
            def __str__(self): events.append("str"); return "marker"
            def __iter__(self): events.append("iter"); return iter(())
        class NonRaising(Colliding):
            __hash__ = Colliding.__hash__
            def __eq__(self, _other): events.append("eq"); return False
        class RequestSubclass(str):
            def __hash__(self): events.append("hash"); return hash("request")
            def __eq__(self, _other): events.append("eq"); return True
        for key in (Colliding(), NonRaising(), RequestSubclass("request")):
            value = payload()
            value[key] = 1
            events.clear()  # dict construction may legitimately hash the key
            with self.subTest(key_type=type(key)):
                with mock.patch.object(adapter, "validate_synthetic_fixture_for_offline_harness") as semantic, \
                     mock.patch.object(factory, "_consume_validated_synthetic_for_test") as consumer:
                    projected, reason, echo = subject._project_minimum_subset(value)
                self.assertIsNone(projected)
                self.assertEqual((reason, echo), ("ROOT_FIELD_BLOCKED", False))
                self.assertEqual(events, [])
                self.assertEqual((semantic.call_count, consumer.call_count), (0, 0))

    def test_handoff_is_issued_once_and_cannot_be_forged_exported_or_replayed(self):
        owner = provider()
        raw = json.dumps(payload(), separators=(",", ":")).encode()
        envelope = preconnection._synthetic_envelope_for_test(
            status=200, media_type="application/json", body=raw, elapsed_ms=1, budget_ms=2,
        )
        handoff = preconnection.issue_syntax_handoff_for_test(
            evidence=preconnection.fixed_evidence_for_test(), envelope=envelope,
            provider=owner, public_id=PUBLIC_IDS[0],
        )
        self.assertIs(type(handoff), preconnection.ValidatedSyntaxHandoff)
        self.assertNotIn(CONTENT, repr(handoff)); self.assertNotIn(TARGET, repr(handoff))
        for operation in (pickle.dumps, copy.copy, copy.deepcopy,
                          lambda value: value.__getstate__(),
                          lambda value: value.__reduce__()):
            with self.subTest(operation=operation):
                with self.assertRaisesRegex(TypeError, "SYNTAX_HANDOFF_EXPORT_FORBIDDEN"):
                    operation(handoff)
        for operation in (vars, asdict, json.dumps):
            with self.subTest(operation=operation):
                with self.assertRaises((TypeError, AttributeError)):
                    operation(handoff)
        with self.assertRaisesRegex(AttributeError, "SYNTAX_HANDOFF_IMMUTABLE"):
            handoff.payload = payload()
        with self.assertRaisesRegex(TypeError, "SYNTAX_HANDOFF_ISSUER_REQUIRED"):
            preconnection.ValidatedSyntaxHandoff()
        unissued = object.__new__(preconnection.ValidatedSyntaxHandoff)
        for candidate, candidate_owner in ((unissued, owner), (handoff, provider())):
            blocked = subject._run_offline_projection_for_test(
                dispositions=subject.fixed_field_dispositions_for_test(), handoff=candidate,
                requested_content_id=CONTENT, provider=candidate_owner, public_id=PUBLIC_IDS[0],
            )
            self.assertEqual(blocked.reason_code, "SYNTAX_HANDOFF_BLOCKED")
        first = subject._run_offline_projection_for_test(
            dispositions=subject.fixed_field_dispositions_for_test(), handoff=handoff,
            requested_content_id=CONTENT, provider=owner, public_id=PUBLIC_IDS[0],
        )
        self.assertEqual(first.status, subject.ACCEPTED)
        replay = subject._run_offline_projection_for_test(
            dispositions=subject.fixed_field_dispositions_for_test(), handoff=handoff,
            requested_content_id=CONTENT, provider=owner, public_id=PUBLIC_IDS[0],
        )
        self.assertEqual(replay.reason_code, "SYNTAX_HANDOFF_BLOCKED")

    def test_matching_handoff_replay_stops_only_that_owner_generation(self):
        owner = provider()
        other = provider()
        raw = json.dumps(payload(), separators=(",", ":")).encode()
        envelope = preconnection._synthetic_envelope_for_test(
            status=200, media_type="application/json", body=raw, elapsed_ms=1, budget_ms=2,
        )
        handoff = preconnection.issue_syntax_handoff_for_test(
            evidence=preconnection.fixed_evidence_for_test(), envelope=envelope,
            provider=owner, public_id=PUBLIC_IDS[0],
        )
        self.assertIs(type(handoff), preconnection.ValidatedSyntaxHandoff)
        unissued = object.__new__(preconnection.ValidatedSyntaxHandoff)
        for candidate in (unissued, handoff):
            blocked = subject._run_offline_projection_for_test(
                dispositions=subject.fixed_field_dispositions_for_test(), handoff=candidate,
                requested_content_id=CONTENT, provider=other, public_id=PUBLIC_IDS[0],
            )
            self.assertEqual(blocked.reason_code, "SYNTAX_HANDOFF_BLOCKED")
        with mock.patch.object(adapter, "validate_synthetic_fixture_for_offline_harness",
                               wraps=adapter.validate_synthetic_fixture_for_offline_harness) as semantic, \
             mock.patch.object(factory, "_consume_validated_synthetic_for_test",
                               wraps=factory._consume_validated_synthetic_for_test) as consumer:
            independent = self.assess(payload(), offline_provider=other)
        self.assertEqual(independent.status, subject.ACCEPTED)
        self.assertEqual((semantic.call_count, consumer.call_count), (1, 1))

        first = subject._run_offline_projection_for_test(
            dispositions=subject.fixed_field_dispositions_for_test(), handoff=handoff,
            requested_content_id=CONTENT, provider=owner, public_id=PUBLIC_IDS[0],
        )
        self.assertEqual(first.status, subject.ACCEPTED)
        replay = subject._run_offline_projection_for_test(
            dispositions=subject.fixed_field_dispositions_for_test(), handoff=handoff,
            requested_content_id=CONTENT, provider=owner, public_id=PUBLIC_IDS[0],
        )
        self.assertEqual(replay.reason_code, "SYNTAX_HANDOFF_BLOCKED")
        for attempt in range(2):
            with self.subTest(fresh_attempt=attempt):
                with mock.patch.object(adapter, "validate_synthetic_fixture_for_offline_harness") as semantic, \
                     mock.patch.object(factory, "_consume_validated_synthetic_for_test") as consumer:
                    later = self.assess(payload(), offline_provider=owner)
                self.assertEqual(later.reason_code, "SYNTAX_GATE_BLOCKED")
                self.assertEqual((semantic.call_count, consumer.call_count), (0, 0))

    def test_composed_syntax_rejects_malformed_bytes_before_semantics(self):
        invalid = (
            b"\xef\xbb\xbf{}", b"\xff", b'{"result":{},"result":{}}',
            b'{"x":NaN}', b'{"x":Infinity}', b'{} trailing',
            b"{}" + b" " * (preconnection.MAX_BODY_BYTES - 1),
            ("[" * 32 + "0" + "]" * 32).encode(),
            ("[" + ",".join("0" for _ in range(preconnection.MAX_JSON_NODES)) + "]").encode(),
            ('"' + "x" * (preconnection.MAX_STRING_TOKEN_BYTES - 1) + '"').encode(),
            ('{"' + "x" * (preconnection.MAX_STRING_TOKEN_BYTES - 1) + '":0}').encode(),
            ("1" * (preconnection.MAX_NUMBER_TOKEN_CHARS + 1)).encode(),
        )
        for raw in invalid:
            with self.subTest(size=len(raw)):
                with mock.patch.object(adapter, "validate_synthetic_fixture_for_offline_harness") as semantic, \
                     mock.patch.object(factory, "_consume_validated_synthetic_for_test") as consumer:
                    receipt = self.assess(raw)
                self.assertEqual(receipt.reason_code, "SYNTAX_GATE_BLOCKED")
                self.assertEqual((semantic.call_count, consumer.call_count), (0, 0))
        for depth in (31, 32, 33):
            raw = "[" * (depth - 1) + "0" + "]" * (depth - 1)
            self.assertEqual(preconnection._scan_json_bounds(raw), depth <= preconnection.MAX_JSON_DEPTH)
        for nodes in (4095, 4096, 4097):
            raw = "[" + ",".join("0" for _ in range(nodes - 1)) + "]"
            self.assertEqual(preconnection._scan_json_bounds(raw), nodes <= preconnection.MAX_JSON_NODES)
        for delta in (-1, 0, 1):
            raw = b"{}" + b" " * (preconnection.MAX_BODY_BYTES - 2 + delta)
            self.assertEqual(preconnection._decode_json(raw) is not None, delta <= 0)
            scalar = '"' + "x" * (preconnection.MAX_STRING_TOKEN_BYTES - 2 + delta) + '"'
            self.assertEqual(preconnection._scan_json_bounds(scalar), delta <= 0)
            self.assertEqual(preconnection._scan_json_bounds("{" + scalar + ":0}"), delta <= 0)
            number = "1" * (preconnection.MAX_NUMBER_TOKEN_CHARS + delta)
            self.assertEqual(preconnection._scan_json_bounds(number), delta <= 0)

    def test_url_byte_boundary_and_terminal_owner_state_use_composed_path(self):
        for multibyte in (False, True):
            for delta in (-1, 0, 1):
                value = payload()
                prefix = TARGET + ("あ" if multibyte else "")
                value["result"]["items"][0]["affiliateURL"] = prefix + "x" * (preconnection.MAX_URL_UTF8_BYTES - len(prefix.encode()) + delta)
                with self.subTest(url_delta=delta, multibyte=multibyte):
                    with mock.patch.object(adapter, "validate_synthetic_fixture_for_offline_harness", wraps=adapter.validate_synthetic_fixture_for_offline_harness) as semantic, \
                         mock.patch.object(factory, "_consume_validated_synthetic_for_test", wraps=factory._consume_validated_synthetic_for_test) as consumer:
                        receipt = self.assess(value)
                    self.assertEqual(semantic.call_count, 0 if delta > 0 else 1)
                    self.assertEqual(consumer.call_count, 0 if delta > 0 else 1)
                    self.assertEqual(receipt.status == subject.ACCEPTED, delta <= 0)
        for changes in ({"kill_before": True}, {"kill_after": True}, {"revoked": True},
                        {"elapsed_ms": -1}, {"elapsed_ms": 2}, {"budget_ms": 0}):
            owner = provider()
            first = self.assess(payload(), offline_provider=owner, envelope_changes=changes)
            self.assertNotEqual(first.status, subject.ACCEPTED)
            with mock.patch.object(adapter, "validate_synthetic_fixture_for_offline_harness") as semantic:
                later = self.assess(payload(), offline_provider=owner)
            self.assertEqual(later.reason_code, "SYNTAX_GATE_BLOCKED")
            self.assertEqual(semantic.call_count, 0)

    def test_composed_bounds_distinguish_syntax_from_disposition(self):
        limits = (
            ("depth", preconnection.MAX_JSON_DEPTH),
            ("nodes", preconnection.MAX_JSON_NODES),
            ("string", preconnection.MAX_STRING_TOKEN_BYTES),
            ("key", preconnection.MAX_STRING_TOKEN_BYTES),
            ("number", preconnection.MAX_NUMBER_TOKEN_CHARS),
        )
        for kind, limit in limits:
            for delta in (-1, 0, 1):
                target = limit + delta
                if kind == "depth":
                    padding = "[" * (target - 2) + "0" + "]" * (target - 2)
                    raw = b'{"padding":' + padding.encode() + b'}'
                elif kind == "nodes":
                    # The normal fixture has ten nodes; this root has one extra key/list.
                    padding = "[" + ",".join("0" for _ in range(target - 2)) + "]"
                    raw = b'{"padding":' + padding.encode() + b'}'
                elif kind == "string":
                    token = '"' + "x" * (target - 2) + '"'
                    raw = b'{"padding":' + token.encode() + b'}'
                elif kind == "key":
                    token = '"' + "x" * (target - 2) + '"'
                    raw = b'{' + token.encode() + b':0}'
                else:
                    raw = b'{"padding":' + ("1" * target).encode() + b'}'
                with self.subTest(kind=kind, delta=delta):
                    with mock.patch.object(adapter, "validate_synthetic_fixture_for_offline_harness") as semantic, \
                         mock.patch.object(factory, "_consume_validated_synthetic_for_test") as consumer:
                        receipt = self.assess(raw)
                    self.assertEqual(receipt.reason_code,
                                     "SYNTAX_GATE_BLOCKED" if delta > 0 else "ROOT_FIELD_BLOCKED")
                    self.assertEqual((semantic.call_count, consumer.call_count), (0, 0))

        base = json.dumps(payload(), separators=(",", ":")).encode()
        for delta in (-1, 0, 1):
            raw = base + b" " * (preconnection.MAX_BODY_BYTES - len(base) + delta)
            with self.subTest(kind="body", delta=delta):
                with mock.patch.object(adapter, "validate_synthetic_fixture_for_offline_harness",
                                       wraps=adapter.validate_synthetic_fixture_for_offline_harness) as semantic, \
                     mock.patch.object(factory, "_consume_validated_synthetic_for_test",
                                       wraps=factory._consume_validated_synthetic_for_test) as consumer:
                    receipt = self.assess(raw)
                self.assertEqual(receipt.reason_code,
                                 "SYNTAX_GATE_BLOCKED" if delta > 0 else "SYNTHETIC_ONLY")
                self.assertEqual((semantic.call_count, consumer.call_count),
                                 (0, 0) if delta > 0 else (1, 1))


if __name__ == "__main__":
    unittest.main()
