import json
from dataclasses import replace, asdict
from pathlib import Path
import sys
import unittest
from unittest import mock
import pickle
import copy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import affiliate_cta_approved_context as approved
import affiliate_cta_network_disabled_wire_adapter as adapter
import affiliate_cta_offline_provider_factory as factory
import affiliate_cta_preconnection_synthetic_envelope as subject
import affiliate_cta_transport_capability_manifest as capability
from datetime import datetime, timezone


CONTENT = "fixture-content_01"
TARGET = "https://al.fanza.co.jp/?lurl=https%3A%2F%2Fexample.invalid%2F"
NOW = datetime(2026, 9, 23, tzinfo=timezone.utc)
PUBLIC_IDS = tuple(f"itm_{number:024x}" for number in range(10))


def payload(**changes):
    result = {"status": 200, "result_count": 1, "total_count": 1, "first_position": 1,
              "items": [{"content_id": CONTENT, "affiliateURL": TARGET}]}
    result.update(changes)
    return {"result": result}


def provider():
    context = approved._make_test_context(PUBLIC_IDS, lambda _value: None)
    mapping = {value: f"other-{index}" for index, value in enumerate(PUBLIC_IDS)}
    mapping[PUBLIC_IDS[0]] = CONTENT
    return factory._build_offline_provider_for_test(context, mapping, lambda _value: None, lambda: NOW)


def envelope(body=None, **changes):
    values = dict(status=200, media_type="application/json; charset=utf-8",
                  body=body if type(body) is bytes else json.dumps(payload() if body is None else body, separators=(",", ":")).encode(),
                  elapsed_ms=1, budget_ms=2)
    values.update(changes)
    return subject._synthetic_envelope_for_test(**values)


class TestPreconnectionSyntheticEnvelope(unittest.TestCase):
    def assess_envelope(self, value, *, evidence=None, offline_provider=None):
        return subject._run_preconnection_synthetic_envelope_for_test(
            evidence=subject.fixed_evidence_for_test() if evidence is None else evidence,
            envelope=value, requested_content_id=CONTENT,
            provider=provider() if offline_provider is None else offline_provider, public_id=PUBLIC_IDS[0],
        )

    def test_safe_fixture_calls_adapter_and_owner_once_with_disabled_receipt(self):
        offline_provider = provider()
        with mock.patch.object(adapter, "validate_synthetic_fixture_for_offline_harness", wraps=adapter.validate_synthetic_fixture_for_offline_harness) as semantic, \
             mock.patch.object(factory, "_consume_validated_synthetic_for_test", wraps=factory._consume_validated_synthetic_for_test) as consumed:
            receipt = self.assess_envelope(envelope(), offline_provider=offline_provider)
        self.assertEqual(receipt.status, subject.ACCEPTED)
        self.assertEqual((semantic.call_count, consumed.call_count), (1, 1))
        self.assertTrue(receipt.adapter_validated); self.assertTrue(receipt.owner_consumed)
        self.assertFalse(receipt.connection_allowed); self.assertFalse(receipt.activation_allowed)
        self.assertFalse(receipt.publication_allowed)
        self.assertEqual((receipt.retry_count, receipt.redirect_count, receipt.real_io_count), (0, 0, 0))

    def test_http_media_and_decode_fail_before_semantics(self):
        invalids = (
            envelope(status=429), envelope(status=500), envelope(media_type="text/html"),
            envelope(media_type="application/json; charset=iso-8859-1"),
            envelope(media_type="application/json; charset=utf-8; charset=utf-8"),
            envelope(media_type="application/json; charset=" + "x" * subject.MAX_MEDIA_TYPE_CHARS),
            envelope(body=b"\xef\xbb\xbf{}"), envelope(body=b'{"x":NaN}'),
            envelope(body=b'{"x":1,"x":2}'), envelope(body=b'{} trailing'),
            envelope(body=b'<xml/>'), envelope(body=b'callback({})'), envelope(body=b'\xff'),
        )
        for value in invalids:
            with self.subTest(case=repr(value)):
                with mock.patch.object(adapter, "validate_synthetic_fixture_for_offline_harness", wraps=adapter.validate_synthetic_fixture_for_offline_harness) as semantic:
                    receipt = self.assess_envelope(value)
                self.assertEqual(semantic.call_count, 0)
                self.assertEqual(receipt.status, subject.BLOCKED)

    def test_bounds_are_inclusive_and_oversize_is_blocked(self):
        exact = b"{" + b" " * (subject.MAX_BODY_BYTES - 2) + b"}"
        for body, expected in ((exact, subject.BLOCKED), (b"x" * (subject.MAX_BODY_BYTES + 1), subject.BLOCKED)):
            # Exact byte size is accepted by the byte gate but fails later JSON semantics; oversize fails earlier.
            with self.subTest(size=len(body)):
                self.assertEqual(self.assess_envelope(envelope(body=body)).status, expected)
        too_long_url = "x" * (subject.MAX_URL_UTF8_BYTES + 1)
        self.assertEqual(self.assess_envelope(envelope({"result": {"affiliateURL": too_long_url}})).status, subject.BLOCKED)
        deep = value = {}
        for _ in range(subject.MAX_JSON_DEPTH + 1):
            nested = {}; value["x"] = nested; value = nested
        self.assertEqual(self.assess_envelope(envelope(deep)).status, subject.BLOCKED)
        wide = {str(index): index for index in range(subject.MAX_JSON_NODES + 1)}
        self.assertEqual(self.assess_envelope(envelope(wide)).status, subject.BLOCKED)

    def test_evidence_unknown_duplicate_superseded_and_c_block(self):
        base = subject.fixed_evidence_for_test()
        c = subject.EvidenceRequirement("LIVE_RESPONSE_CONTRACT_UNCONFIRMED", subject.UNCONFIRMED_BLOCKED, "x", "x", "x", "x")
        bad = (
            (), base + (base[0],), base + (c,),
            (subject.EvidenceRequirement(base[0].topic_id, base[0].classification, base[0].source_reference, base[0].source_digest, base[0].source_checked_at, base[0].scope, True), base[1]),
        )
        for evidence in bad:
            with self.subTest(size=len(evidence)):
                self.assertEqual(self.assess_envelope(envelope(), evidence=evidence).reason_code, "EVIDENCE_BLOCKED")

    def test_semantic_zero_extra_and_echo_do_not_strip(self):
        bad = (payload(result_count=0), {"request": {}, **payload()}, {"result": {**payload()["result"], "unknown": 1}})
        for body in bad:
            with self.subTest(body_type=type(body)):
                receipt = self.assess_envelope(envelope(body))
                self.assertEqual(receipt.reason_code, "SEMANTIC_VALIDATION_BLOCKED")

    def test_attempt_deadline_kill_replay_and_owner_failure_are_terminal(self):
        for value in (envelope(elapsed_ms=-1), envelope(elapsed_ms=2), envelope(budget_ms=0),
                      envelope(kill_before=True), envelope(kill_after=True), envelope(revoked=True)):
            with self.subTest(value=value):
                self.assertNotEqual(self.assess_envelope(value).status, subject.ACCEPTED)
        replay = envelope()
        self.assertEqual(self.assess_envelope(replay).status, subject.ACCEPTED)
        self.assertEqual(self.assess_envelope(replay).reason_code, "ATTEMPT_ALREADY_CONSUMED")
        self.assertEqual(self.assess_envelope(envelope(), offline_provider=object()).reason_code, "OWNER_BLOCKED")

    def test_defaults_remain_production_blocked_and_receipts_hide_values(self):
        receipt = self.assess_envelope(envelope(body=payload(result_count=0)))
        self.assertNotIn(CONTENT, repr(receipt)); self.assertNotIn(TARGET, repr(receipt))
        self.assertIsNone(subject.production_policy())
        self.assertIsNone(adapter.production_adapter())
        self.assertIsNone(capability.OFFICIAL_WIRE_CONTRACT_VERSION)
        self.assertIsNone(subject.OFFICIAL_WIRE_CONTRACT_VERSION)

    def test_standard_runner_executes_discovered_methods(self):
        # Regression for accidentally shadowing TestCase.run.
        self.assertIs(self.__class__.run, unittest.TestCase.run)
        names = unittest.defaultTestLoader.getTestCaseNames(self.__class__)
        self.assertGreaterEqual(len(names), 7)

    def test_evidence_exact_primitives_block_before_adapter_or_owner_consumer(self):
        base = subject.fixed_evidence_for_test()
        events = []
        class Hostile:
            def __eq__(self, _other):
                events.append("eq")
                return True
            def __hash__(self):
                events.append("hash")
                return 1
            def __iter__(self):
                events.append("iter")
                return iter(())
            def __repr__(self):
                events.append("repr")
                return "private-marker"
        class StringSubclass(str):
            pass
        cases = [
            (), base + (base[0],), base + (subject.EvidenceRequirement(
                "LIVE_RESPONSE_CONTRACT_UNCONFIRMED", subject.UNCONFIRMED_BLOCKED, "x", "x", "x", "x"),),
            (replace(base[0], topic_id="UNKNOWN"), base[1]),
            (replace(base[0], classification=subject.PROJECT_CONTROL), base[1]),
            (replace(base[0], source_digest="wrong"), base[1]),
            (base[0], replace(base[1], scope="other")),
            (base[0], replace(base[1], source_digest="other-version")),
            (base[0], replace(base[1], project_control_version="other-version")),
            (replace(base[0], source_reference=base[1].source_reference), base[1]),
            (base[1], replace(base[0], topic_id=base[1].topic_id)),
        ]
        for field in ("topic_id", "classification", "source_reference", "source_digest", "source_checked_at", "scope", "project_control_version"):
            cases.append((replace(base[0], **{field: Hostile()}), base[1]))
            cases.append((replace(base[0], **{field: StringSubclass(getattr(base[0], field))}), base[1]))
        for value in (True, 1, 0, "true", None, Hostile()):
            cases.append((replace(base[0], superseded=value), base[1]))
        with mock.patch.object(adapter, "validate_synthetic_fixture_for_offline_harness") as semantic, \
             mock.patch.object(factory, "_consume_validated_synthetic_for_test") as consumer:
            for evidence in cases:
                with self.subTest(case=len(evidence)):
                    receipt = self.assess_envelope(envelope(), evidence=evidence)
                    self.assertEqual(receipt.reason_code, "EVIDENCE_BLOCKED")
                    self.assertFalse(receipt.connection_allowed)
        self.assertEqual((semantic.call_count, consumer.call_count), (0, 0))
        self.assertEqual(events, [])

    def test_issued_envelope_is_immutable_and_factory_rejects_hostile_values(self):
        issued = envelope()
        for name, value in (("status", 200.0), ("elapsed_ms", float("nan")), ("kill_before", 1), ("body", b"{}")):
            with self.subTest(field=name):
                with self.assertRaisesRegex(AttributeError, "SYNTHETIC_ENVELOPE_IMMUTABLE"):
                    setattr(issued, name, value)
        events = []
        class Hostile:
            def __bool__(self):
                events.append("bool")
                return False
            def __getattribute__(self, _name):
                events.append("attribute")
                raise RuntimeError("private-marker")
            def __repr__(self):
                events.append("repr")
                return "private-marker"
        for changes in ({"status": True}, {"status": 200.0}, {"status": Hostile()},
                        {"elapsed_ms": float("nan")}, {"elapsed_ms": float("inf")},
                        {"kill_before": Hostile()}, {"body": Hostile()}):
            with self.subTest(fields=tuple(changes)):
                inputs = dict(status=200, media_type="application/json", body=b"{}",
                              elapsed_ms=1, budget_ms=2)
                inputs.update(changes)
                self.assertIsNone(subject._synthetic_envelope_for_test(**inputs))
        self.assertEqual(events, [])
        self.assertEqual(self.assess_envelope(issued).status, subject.ACCEPTED)

    def test_non_200_stops_before_body_decode_and_semantics(self):
        for status in (0, 201, 429, 500):
            with self.subTest(status=status):
                owner = provider()
                with mock.patch.object(subject, "_decode_json") as decode, \
                     mock.patch.object(adapter, "validate_synthetic_fixture_for_offline_harness") as semantic, \
                     mock.patch.object(factory, "_consume_validated_synthetic_for_test") as consumer:
                    result = self.assess_envelope(envelope(status=status, body=b"not-json"), offline_provider=owner)
                self.assertEqual(result.reason_code, "HTTP_STATUS_BLOCKED")
                self.assertEqual((decode.call_count, semantic.call_count, consumer.call_count), (0, 0, 0))
                self.assertEqual(self.assess_envelope(envelope(), offline_provider=owner).reason_code, "OWNER_BLOCKED")

    def test_terminal_events_stop_owner_run_across_new_envelopes(self):
        cases = ({"kill_before": True}, {"kill_after": True}, {"revoked": True},
                 {"elapsed_ms": -1}, {"elapsed_ms": 2}, {"budget_ms": 0},
                 {"media_type": "text/html"}, {"body": b"not-json"})
        for changes in cases:
            with self.subTest(fields=tuple(changes)):
                owner = provider()
                first = self.assess_envelope(envelope(**changes), offline_provider=owner)
                self.assertNotEqual(first.status, subject.ACCEPTED)
                with mock.patch.object(adapter, "validate_synthetic_fixture_for_offline_harness") as semantic, \
                     mock.patch.object(factory, "_consume_validated_synthetic_for_test") as consumer:
                    later = self.assess_envelope(envelope(), offline_provider=owner)
                self.assertEqual(later.reason_code, "OWNER_BLOCKED")
                self.assertEqual((semantic.call_count, consumer.call_count), (0, 0))
                self.assertEqual(self.assess_envelope(envelope(), offline_provider=provider()).status, subject.ACCEPTED)

    def test_consumer_rejection_or_exception_stops_owner_and_redacts_receipt(self):
        for replacement in (False, 0, {}, object(), RuntimeError("private-marker")):
            with self.subTest(result_type=type(replacement)):
                owner = provider()
                patch_args = ({"side_effect": replacement} if type(replacement) is RuntimeError
                              else {"return_value": replacement})
                with mock.patch.object(factory, "_consume_validated_synthetic_for_test", **patch_args) as consumer:
                    first = self.assess_envelope(envelope(), offline_provider=owner)
                self.assertEqual(consumer.call_count, 1)
                self.assertEqual(first.reason_code, "OWNER_CONSUMPTION_BLOCKED" if type(replacement) is not RuntimeError else "INTERNAL_FAILURE")
                self.assertFalse(first.owner_consumed)
                self.assertNotIn("private-marker", repr(first))
                with mock.patch.object(adapter, "validate_synthetic_fixture_for_offline_harness") as semantic:
                    later = self.assess_envelope(envelope(), offline_provider=owner)
                self.assertEqual(later.reason_code, "OWNER_BLOCKED")
                self.assertEqual(semantic.call_count, 0)

    def test_non_success_never_reads_snapshot_body(self):
        original = subject._IssuedEnvelope.__getattribute__
        reads = []
        def guarded(instance, name):
            if name == "body":
                reads.append("body")
                raise RuntimeError("private-marker")
            return original(instance, name)
        with mock.patch.object(subject._IssuedEnvelope, "__getattribute__", guarded):
            receipt = self.assess_envelope(envelope(status=429, body=b"private-marker"))
        self.assertEqual(receipt.reason_code, "HTTP_STATUS_BLOCKED")
        self.assertEqual(reads, [])

    def test_lexical_bounds_before_materialization(self):
        # Node count includes root and all value/container nodes; object keys are excluded.
        for count in (4095, 4096, 4097):
            body = ("[" + ",".join("0" for _ in range(count - 1)) + "]").encode()
            with self.subTest(nodes=count):
                self.assertEqual(subject._scan_json_bounds(body.decode()), count <= subject.MAX_JSON_NODES)
        for depth in (31, 32, 33):
            raw = ("[" * (depth - 1) + "0" + "]" * (depth - 1)).encode()
            with self.subTest(depth=depth):
                self.assertEqual(subject._scan_json_bounds(raw.decode()), depth <= subject.MAX_JSON_DEPTH)
        for delta in (-1, 0, 1):
            raw = b"{}" + b" " * (subject.MAX_BODY_BYTES - 2 + delta)
            with self.subTest(body_delta=delta):
                with mock.patch.object(subject, "_scan_json_bounds", wraps=subject._scan_json_bounds) as scan:
                    decoded = subject._decode_json(raw)
                self.assertEqual(decoded is not None, delta <= 0)
                self.assertEqual(scan.call_count, 0 if delta > 0 else 1)
        for delta in (-1, 0, 1):
            # One three-byte Japanese character plus ASCII padding, measured after JSON decode.
            value = "あ" + "x" * (subject.MAX_URL_UTF8_BYTES - 3 + delta)
            raw = json.dumps({"affiliateURL": value}, ensure_ascii=False)
            with self.subTest(url_delta=delta):
                self.assertEqual(subject._scan_json_bounds(raw), delta <= 0)
        for delta in (-1, 0, 1):
            raw = '"' + "x" * (subject.MAX_STRING_TOKEN_BYTES - 2 + delta) + '"'
            with self.subTest(string_delta=delta):
                self.assertEqual(subject._scan_json_bounds(raw), delta <= 0)
            key_raw = '{' + raw + ':0}'
            self.assertEqual(subject._scan_json_bounds(key_raw), delta <= 0)
            numeric = "1" * (subject.MAX_NUMBER_TOKEN_CHARS + delta)
            self.assertEqual(subject._scan_json_bounds(numeric), delta <= 0)
        huge_array = ("[" + ",".join("0" for _ in range(subject.MAX_JSON_NODES)) + "]").encode()
        with mock.patch.object(subject.json, "loads", side_effect=AssertionError("materialized")) as loads:
            self.assertIsNone(subject._decode_json(huge_array))
        self.assertEqual(loads.call_count, 0)

    def test_each_overlimit_bound_stops_at_decode_before_semantics(self):
        bodies = (
            b"{}" + b" " * (subject.MAX_BODY_BYTES - 1),
            ("[" * 32 + "0" + "]" * 32).encode(),
            ("[" + ",".join("0" for _ in range(subject.MAX_JSON_NODES)) + "]").encode(),
            ('"' + "x" * (subject.MAX_STRING_TOKEN_BYTES - 1) + '"').encode(),
            ('{"' + "x" * (subject.MAX_STRING_TOKEN_BYTES - 1) + '":0}').encode(),
            ("1" * (subject.MAX_NUMBER_TOKEN_CHARS + 1)).encode(),
            json.dumps({"affiliateURL": "あ" + "x" * (subject.MAX_URL_UTF8_BYTES - 2)}, ensure_ascii=False).encode(),
        )
        for body in bodies:
            with self.subTest(byte_length=len(body)):
                with mock.patch.object(adapter, "validate_synthetic_fixture_for_offline_harness") as semantic, \
                     mock.patch.object(factory, "_consume_validated_synthetic_for_test") as consumer:
                    result = self.assess_envelope(envelope(body=body))
                self.assertEqual(result.reason_code, "DECODE_BLOCKED")
                self.assertEqual((semantic.call_count, consumer.call_count), (0, 0))

    def test_receipt_and_envelope_exports_remain_value_free(self):
        issued = envelope()
        receipt = self.assess_envelope(issued)
        for rendered in (repr(receipt), json.dumps(asdict(receipt)), repr(issued)):
            self.assertNotIn(CONTENT, rendered)
            self.assertNotIn(TARGET, rendered)
        for operation in (copy.copy, copy.deepcopy, pickle.dumps, lambda value: value.__getstate__()):
            with self.subTest(operation=operation):
                with self.assertRaisesRegex(TypeError, "SYNTHETIC_ENVELOPE_EXPORT_FORBIDDEN"):
                    operation(issued)


if __name__ == "__main__":
    unittest.main()
