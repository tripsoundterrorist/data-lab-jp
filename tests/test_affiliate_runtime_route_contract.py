from pathlib import Path
import json
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import affiliate_runtime_route_contract as route  # noqa: E402


PUBLIC_ID = "itm_0123456789abcdef01234567"


def assess(**changes):
    values = {
        "route_version": route.ROUTE_VERSION,
        "method": "GET",
        "path": f"/go/{PUBLIC_ID}",
        "request_body_present": False,
        "official_answer_candidate": True,
        "publication_gate_overall_eligible": True,
        "runtime_chain_connected": True,
        "rate_limit_allowed": True,
        "pr_disclosure_available": True,
    }
    values.update(changes)
    return route.assess_route_request(**values)


class AffiliateRuntimeRouteContractTests(unittest.TestCase):
    def test_complete_get_is_only_a_pipeline_candidate(self):
        result = assess()
        self.assertEqual(result.status, route.ROUTE_CANDIDATE)
        self.assertEqual(result.response_status, 302)
        self.assertTrue(result.pipeline_invocation_candidate)
        self.assertFalse(result.redirect_location_present)
        self.assertFalse(result.response_body_allowed)
        self.assertIn(("Cache-Control", "no-store, max-age=0"), result.response_headers)

    def test_head_uses_the_same_bodyless_boundary(self):
        result = assess(method="HEAD")
        self.assertEqual(result.status, route.ROUTE_CANDIDATE)
        self.assertFalse(result.request_body_accepted)
        self.assertFalse(result.response_body_allowed)

    def test_non_allowlisted_methods_stop_before_pipeline(self):
        for method in ("POST", "PUT", "DELETE", "OPTIONS", "get", ""):
            with self.subTest(method=method):
                result = assess(method=method)
                self.assertEqual(result.response_status, 405)
                self.assertFalse(result.pipeline_invocation_candidate)

    def test_route_rejects_queries_fragments_encoding_and_traversal(self):
        for path in (
            f"/go/{PUBLIC_ID}?source=x",
            f"/go/{PUBLIC_ID}#fragment",
            "/go/../secret",
            "/go/%2e%2e%2fsecret",
            "/go/itm_0123456789ABCDEF01234567",
            f"//go/{PUBLIC_ID}",
        ):
            with self.subTest(path=path):
                result = assess(path=path)
                self.assertEqual(result.response_status, 404)
                self.assertFalse(result.pipeline_invocation_candidate)

    def test_request_body_is_never_accepted(self):
        result = assess(request_body_present=True)
        self.assertEqual(result.response_status, 400)
        self.assertFalse(result.request_body_accepted)
        self.assertFalse(result.pipeline_invocation_candidate)

    def test_rate_limit_stops_before_other_activation_guards(self):
        result = assess(
            rate_limit_allowed=False,
            official_answer_candidate=False,
            publication_gate_overall_eligible=False,
        )
        self.assertEqual(result.response_status, 429)
        self.assertEqual(result.reason_codes, ("RATE_LIMIT_BLOCKED",))
        self.assertFalse(result.pipeline_invocation_candidate)

    def test_each_closed_activation_guard_blocks_without_redirect(self):
        for field, reason in (
            ("official_answer_candidate", "OFFICIAL_ANSWER_GATE_CLOSED"),
            ("publication_gate_overall_eligible", "PUBLICATION_GATE_CLOSED"),
            ("runtime_chain_connected", "RUNTIME_CHAIN_NOT_CONNECTED"),
            ("pr_disclosure_available", "PR_DISCLOSURE_NOT_READY"),
        ):
            with self.subTest(field=field):
                result = assess(**{field: False})
                self.assertEqual(result.response_status, 404)
                self.assertIn(reason, result.reason_codes)
                self.assertFalse(result.pipeline_invocation_candidate)
                self.assertFalse(result.redirect_location_present)

    def test_unknown_version_and_non_boolean_guard_fail_closed(self):
        for changes in (
            {"route_version": "9"},
            {"rate_limit_allowed": 1},
            {"method": None},
            {"path": None},
        ):
            with self.subTest(changes=changes):
                result = assess(**changes)
                self.assertEqual(result.status, route.FAIL_CLOSED)
                self.assertEqual(result.response_status, 404)
                self.assertFalse(result.pipeline_invocation_candidate)

    def test_safe_result_contains_no_request_identifier_or_url(self):
        result = assess()
        output = json.dumps(result.to_dict(), sort_keys=True)
        self.assertNotIn(PUBLIC_ID, output)
        self.assertNotIn("/go/", output)
        self.assertNotIn("http", output.lower())
        self.assertFalse(result.redirect_location_present)
        self.assertNotIn("Location", dict(result.response_headers))


if __name__ == "__main__":
    unittest.main()
