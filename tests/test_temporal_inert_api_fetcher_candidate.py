from pathlib import Path
import json
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import temporal_inert_api_fetcher_candidate as candidate  # noqa: E402
import temporal_isolated_collector_response_bridge as bridge  # noqa: E402
from temporal_runbook_policy import FIXED_POPULATIONS  # noqa: E402


def payload(identity, *, extra=False):
    item = {"content_id": f"private-{identity[0]}-{identity[1]}"}
    if extra:
        item["title"] = "must-not-cross-boundary"
    return {"result": {"status": 200, "result_count": "1", "items": [item]}}


class TemporalInertApiFetcherCandidateTests(unittest.TestCase):
    def test_fixed_requests_contain_public_parameters_only(self):
        for identity in FIXED_POPULATIONS:
            request = candidate.prepare_request(identity)
            self.assertFalse(request.executable)
            self.assertFalse(request.live_api_request_authorized)
            self.assertFalse(request.credentials_access_authorized)
            self.assertFalse(request.state_write_authorized)
            self.assertFalse(request.scheduler_change_authorized)
            self.assertFalse(request.production_write_authorized)
            self.assertFalse(request.deploy_allowed)
            self.assertEqual(set(request.query), candidate.REQUEST_QUERY_FIELDS)
            rendered = json.dumps(request.to_dict()).casefold()
            self.assertNotIn("private-", rendered)
            self.assertNotIn("credential_value", rendered)

    def test_request_outside_fixed_plan_is_rejected(self):
        for identity in (
            ("date", 1, 100), ("rank", 1, 99), ["rank", 1, 100],
            ("rank", [], 100),
        ):
            with self.subTest(identity=identity), self.assertRaises(ValueError):
                candidate.prepare_request(identity)

    def test_response_is_reduced_to_exact_bridge_shape(self):
        identity = FIXED_POPULATIONS[0]
        reduced = candidate.reduce_response(
            identity, http_status=200, payload=payload(identity, extra=True)
        )
        self.assertEqual(set(reduced), bridge.RESPONSE_FIELDS)
        self.assertEqual(set(reduced["request"]), bridge.REQUEST_FIELDS)
        self.assertEqual(set(reduced["items"][0]), bridge.ITEM_FIELDS)
        self.assertNotIn("title", json.dumps(reduced))

    def test_status_and_transport_failures_are_bounded(self):
        identity = FIXED_POPULATIONS[0]
        cases = (
            (candidate.reduce_response(identity, http_status=429, payload={}), "RATE_LIMIT"),
            (candidate.reduce_response(identity, http_status=500, payload={}), "HTTP_ERROR"),
            (candidate.classify_transport_failure(identity, "TIMEOUT"), "HTTP_ERROR"),
            (candidate.classify_transport_failure(identity, RuntimeError("secret")), "API_ERROR"),
            (candidate.classify_transport_failure(identity, {"secret": "value"}), "API_ERROR"),
        )
        for result, expected in cases:
            self.assertFalse(result["success"])
            self.assertEqual(result["error_classification"], expected)
            self.assertNotIn("secret", json.dumps(result))

    def test_malformed_payload_fails_closed_without_echo(self):
        identity = FIXED_POPULATIONS[0]
        malformed = {"result": {"status": 200, "result_count": 1,
                                "items": [{"title": "private-title"}]}}
        result = candidate.reduce_response(identity, http_status=200, payload=malformed)
        self.assertEqual(result["error_classification"], "API_ERROR")
        self.assertNotIn("private-title", json.dumps(result))

    def test_module_has_no_network_or_environment_capability(self):
        source = (ROOT / "scripts" / "temporal_inert_api_fetcher_candidate.py").read_text()
        for forbidden in ("urllib.request", "requests", "os.environ", "dotenv", "urlopen"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
