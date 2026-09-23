import json
from pathlib import Path
import sys
import unittest
from unittest import mock

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
    def run(self, value, *, evidence=None, offline_provider=None):
        return subject._run_preconnection_synthetic_envelope_for_test(
            evidence=subject.fixed_evidence_for_test() if evidence is None else evidence,
            envelope=value, requested_content_id=CONTENT,
            provider=provider() if offline_provider is None else offline_provider, public_id=PUBLIC_IDS[0],
        )

    def test_safe_fixture_calls_adapter_and_owner_once_with_disabled_receipt(self):
        offline_provider = provider()
        with mock.patch.object(adapter, "validate_synthetic_fixture_for_offline_harness", wraps=adapter.validate_synthetic_fixture_for_offline_harness) as semantic, \
             mock.patch.object(factory, "_consume_validated_synthetic_for_test", wraps=factory._consume_validated_synthetic_for_test) as consumed:
            receipt = self.run(envelope(), offline_provider=offline_provider)
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
            envelope(body=b"\xef\xbb\xbf{}"), envelope(body=b'{"x":NaN}'),
            envelope(body=b'{"x":1,"x":2}'), envelope(body=b'{} trailing'),
            envelope(body=b'<xml/>'), envelope(body=b'callback({})'), envelope(body=b'\xff'),
        )
        for value in invalids:
            with self.subTest(media=value.media_type, status=value.status):
                with mock.patch.object(adapter, "validate_synthetic_fixture_for_offline_harness", wraps=adapter.validate_synthetic_fixture_for_offline_harness) as semantic:
                    receipt = self.run(value)
                self.assertEqual(semantic.call_count, 0)
                self.assertEqual(receipt.status, subject.BLOCKED)

    def test_bounds_are_inclusive_and_oversize_is_blocked(self):
        exact = b"{" + b" " * (subject.MAX_BODY_BYTES - 2) + b"}"
        for body, expected in ((exact, subject.BLOCKED), (b"x" * (subject.MAX_BODY_BYTES + 1), subject.BLOCKED)):
            # Exact byte size is accepted by the byte gate but fails later JSON semantics; oversize fails earlier.
            with self.subTest(size=len(body)):
                self.assertEqual(self.run(envelope(body=body)).status, expected)
        too_long_url = "x" * (subject.MAX_URL_UTF8_BYTES + 1)
        self.assertEqual(self.run(envelope({"result": {"affiliateURL": too_long_url}})).status, subject.BLOCKED)
        deep = value = {}
        for _ in range(subject.MAX_JSON_DEPTH + 1):
            nested = {}; value["x"] = nested; value = nested
        self.assertEqual(self.run(envelope(deep)).status, subject.BLOCKED)
        wide = {str(index): index for index in range(subject.MAX_JSON_NODES + 1)}
        self.assertEqual(self.run(envelope(wide)).status, subject.BLOCKED)

    def test_evidence_unknown_duplicate_superseded_and_c_block(self):
        base = subject.fixed_evidence_for_test()
        c = subject.EvidenceRequirement("LIVE_RESPONSE_CONTRACT_UNCONFIRMED", subject.UNCONFIRMED_BLOCKED, "x", "x", "x", "x")
        bad = (
            (), base + (base[0],), base + (c,),
            (subject.EvidenceRequirement(base[0].topic_id, base[0].classification, base[0].source_reference, base[0].source_digest, base[0].source_checked_at, base[0].scope, True), base[1]),
        )
        for evidence in bad:
            with self.subTest(size=len(evidence)):
                self.assertEqual(self.run(envelope(), evidence=evidence).reason_code, "EVIDENCE_BLOCKED")

    def test_semantic_zero_extra_and_echo_do_not_strip(self):
        bad = (payload(result_count=0), {"request": {}, **payload()}, {"result": {**payload()["result"], "unknown": 1}})
        for body in bad:
            with self.subTest(body_type=type(body)):
                receipt = self.run(envelope(body))
                self.assertEqual(receipt.reason_code, "SEMANTIC_VALIDATION_BLOCKED")

    def test_attempt_deadline_kill_replay_and_owner_failure_are_terminal(self):
        for value in (envelope(elapsed_ms=-1), envelope(elapsed_ms=2), envelope(budget_ms=0),
                      envelope(kill_before=True), envelope(kill_after=True), envelope(revoked=True)):
            with self.subTest(value=value):
                self.assertNotEqual(self.run(value).status, subject.ACCEPTED)
        replay = envelope()
        self.assertEqual(self.run(replay).status, subject.ACCEPTED)
        self.assertEqual(self.run(replay).reason_code, "ATTEMPT_ALREADY_CONSUMED")
        self.assertEqual(self.run(envelope(), offline_provider=object()).reason_code, "OWNER_BLOCKED")

    def test_defaults_remain_production_blocked_and_receipts_hide_values(self):
        receipt = self.run(envelope(body=payload(result_count=0)))
        self.assertNotIn(CONTENT, repr(receipt)); self.assertNotIn(TARGET, repr(receipt))
        self.assertIsNone(subject.production_policy())
        self.assertIsNone(adapter.production_adapter())
        self.assertIsNone(capability.OFFICIAL_WIRE_CONTRACT_VERSION)
        self.assertIsNone(subject.OFFICIAL_WIRE_CONTRACT_VERSION)


if __name__ == "__main__":
    unittest.main()
