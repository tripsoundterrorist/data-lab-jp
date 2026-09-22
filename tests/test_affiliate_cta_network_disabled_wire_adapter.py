from pathlib import Path
import inspect
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import affiliate_cta_canary_offline_candidate as render
import affiliate_cta_click_revalidation_candidate as click
import affiliate_cta_network_disabled_wire_adapter as subject
import affiliate_cta_production_composition as composition
import affiliate_cta_runtime_inert_integration as route
import affiliate_cta_transport_capability_manifest as capability


CONTENT = "fixture-content_01"
TARGET = "https://al.fanza.co.jp/?lurl=https%3A%2F%2Fexample.invalid%2F"


def fixture(content_id=CONTENT, affiliate_url=TARGET):
    return {"result": {"status": 200, "items": [{"content_id": content_id, "affiliateURL": affiliate_url}]}}


class NetworkDisabledWireAdapterTests(unittest.TestCase):
    def test_canonical_plan_is_fixed_redacted_and_network_disabled(self):
        api, affiliate = subject._secret_handles_for_test()
        plan = subject._build_canonical_plan_for_test(content_id=CONTENT, api_handle=api, affiliate_handle=affiliate)
        self.assertEqual(plan.method, "GET")
        self.assertEqual(plan.endpoint, "https://api.dmm.com/affiliate/v3/ItemList")
        self.assertEqual(plan.encoding, "utf-8")
        self.assertEqual(plan.parameter_names, ("api_id", "affiliate_id", "site", "service", "floor", "cid", "hits", "offset", "output"))
        self.assertEqual((plan.site, plan.service, plan.floor, plan.hits, plan.offset, plan.output), ("FANZA", "digital", "videoa", 1, 1, "json"))
        self.assertTrue(plan.cid_present)
        self.assertFalse(plan.query_completed); self.assertFalse(plan.network_allowed)
        self.assertNotIn(CONTENT, repr(plan)); self.assertNotIn("secret", repr(plan).lower())

    def test_utf8_escape_and_cid_boundaries_are_pure(self):
        self.assertEqual(subject._encode_cid_for_test("a_b-1.2"), "a_b-1.2")
        self.assertEqual(subject._escape_utf8_component_for_test("あ"), "%E3%81%82")
        for value in ("", "bad value", "x" * 129, True, 1, object()):
            with self.subTest(value_type=type(value)):
                self.assertIsNone(subject._encode_cid_for_test(value))
        api, affiliate = subject._secret_handles_for_test()
        self.assertIsNone(subject._build_canonical_plan_for_test(content_id="bad value", api_handle=api, affiliate_handle=affiliate))
        for name, value in (("sort", "rank"), ("site", "DMM.com"), ("service", "other"), ("floor", "other"), ("hits", 2), ("offset", 2), ("output", "xml"), ("keyword", "x"), ("callback", "x")):
            with self.subTest(name=name):
                with self.assertRaises(TypeError):
                    subject._build_canonical_plan_for_test(content_id=CONTENT, api_handle=api, affiliate_handle=affiliate, **{name: value})

    def test_secret_handles_never_accept_values_or_complete_queries(self):
        api, affiliate = subject._secret_handles_for_test()
        self.assertEqual(repr(api), "<OpaqueSecretHandle>")
        self.assertIsNone(subject._build_canonical_plan_for_test(content_id=CONTENT, api_handle="value", affiliate_handle=affiliate))
        self.assertIsNone(subject._build_canonical_plan_for_test(content_id=CONTENT, api_handle=api, affiliate_handle=api))
        self.assertNotIn("value", repr(api))

    def test_strict_fixture_parser_accepts_only_one_exact_observed_url(self):
        observation = subject._parse_fixture_for_test(fixture(), CONTENT)
        self.assertIsNotNone(observation)
        self.assertEqual(repr(observation), "<FixtureObservation>")
        cases = (
            {}, {"result": {"status": "200", "items": []}},
            {"result": {"status": 200, "items": []}},
            fixture(content_id="other"),
            {"result": {"status": 200, "items": [fixture()["result"]["items"][0], fixture()["result"]["items"][0]]}},
            {"result": {"status": 200, "items": [{"content_id": CONTENT, "affiliateURL": 1}]}},
            {"result": {"status": 200, "items": [{"content_id": CONTENT, "affiliateURL": TARGET, "unknown": {}}]}},
            {"result": {"status": 429, "items": []}}, {"error": "unknown"},
        )
        for value in cases:
            with self.subTest(value_type=type(value)):
                self.assertIsNone(subject._parse_fixture_for_test(value, CONTENT))

    def test_fixture_parser_redacts_malicious_objects_and_never_raises(self):
        class Explodes:
            def __eq__(self, _other): raise RuntimeError("private-marker")
            def __hash__(self): return 1
            def __repr__(self): return "private-marker"
        self.assertIsNone(subject._parse_fixture_for_test({Explodes(): object()}, CONTENT))
        self.assertIsNone(subject._parse_fixture_for_test(fixture(affiliate_url=Explodes()), CONTENT))

    def test_credit_metadata_is_inert_and_references_existing_policy(self):
        metadata = subject.credit_disclosure_metadata()
        self.assertTrue(metadata.credit_display_required)
        self.assertFalse(metadata.html_change_allowed); self.assertFalse(metadata.publication_allowed)
        self.assertEqual(metadata.disclosure_policy_reference, "0.1")

    def test_no_production_adapter_or_wire_version_activation(self):
        self.assertIsNone(subject.production_adapter())
        self.assertIsNone(composition.production_provider())
        self.assertIsNone(subject.OFFICIAL_WIRE_CONTRACT_VERSION)
        self.assertEqual(capability.evaluate_connection_preflight(
            manifest=capability.disabled_manifest(), setting_names=(),
            clock_contract=capability.disabled_clock_contract(), kill_runbook=capability.disabled_kill_runbook(),
        ).status, capability.BLOCKED)

    def test_public_entries_cannot_inject_candidate_or_transport_controls(self):
        forbidden = {"adapter", "manifest", "settings", "transport", "clock", "secret", "handle", "fixture", "send"}
        for entry in (click.decide, render.render, route.assess):
            with self.subTest(entry=entry.__name__):
                self.assertTrue(forbidden.isdisjoint(inspect.signature(entry).parameters))


if __name__ == "__main__":
    unittest.main()
