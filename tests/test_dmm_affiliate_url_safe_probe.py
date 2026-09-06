from contextlib import redirect_stdout
from io import BytesIO, StringIO
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.error
import urllib.parse
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "probe-dmm-affiliate-url.py"
SPEC = importlib.util.spec_from_file_location("dmm_affiliate_url_probe", SCRIPT)
probe = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = probe
SPEC.loader.exec_module(probe)


API_ID = "test-api-secret"
AFFILIATE_ID = "test-affiliate-secret"
DUMMY_URL = "https://al.dmm.co.jp/?opaque=test-only"


class FakeResponse(BytesIO):
    def __init__(self, payload: object, status: int = 200):
        super().__init__(json.dumps(payload).encode("utf-8"))
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def payload(affiliate_url: object = DUMMY_URL) -> dict:
    item = {
        "content_id": "sensitive-content-id",
        "title": "sensitive title",
    }
    if affiliate_url is not None:
        item["affiliateURL"] = affiliate_url
    return {
        "result": {
            "status": 200,
            "result_count": 1,
            "items": [item],
        }
    }


class DmmAffiliateUrlSafeProbeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.env_path = Path(self.temporary.name) / ".env"
        self.env_path.write_text(
            f"DMM_API_ID={API_ID}\nDMM_AFFILIATE_ID={AFFILIATE_ID}\n",
            encoding="utf-8",
        )

    def test_dry_run_validates_environment_without_request(self):
        calls = []

        result = probe.run_probe(
            env_path=self.env_path,
            dry_run=True,
            fetcher=lambda *_args, **_kwargs: calls.append("request"),
        )

        self.assertEqual(result.status, probe.DRY_RUN_READY)
        self.assertFalse(result.request_performed)
        self.assertEqual(calls, [])

    def test_one_request_confirms_safe_shape_without_echoing_response(self):
        requests = []

        def fetcher(request, timeout):
            requests.append((request, timeout))
            return FakeResponse(payload())

        result = probe.run_probe(env_path=self.env_path, fetcher=fetcher)

        self.assertEqual(result.status, probe.PASS)
        self.assertTrue(result.request_performed)
        self.assertTrue(result.http_success)
        self.assertTrue(result.api_success)
        self.assertEqual(result.returned_count, 1)
        self.assertTrue(result.affiliate_link_present)
        self.assertTrue(result.https_required_pass)
        self.assertTrue(result.approved_host_pass)
        self.assertTrue(result.host_matches_dmm_co_jp)
        self.assertFalse(result.host_matches_dmm_com)
        self.assertFalse(result.host_matches_fanza_com)
        self.assertFalse(result.host_matches_fanza_co_jp)
        self.assertFalse(result.host_unclassified)
        self.assertTrue(result.embedded_credentials_absent)
        self.assertTrue(result.url_length_bounded)
        self.assertFalse(result.response_persisted)
        self.assertFalse(result.database_write_performed)
        self.assertEqual(len(requests), 1)

        request, timeout = requests[0]
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(request.full_url).query)
        self.assertEqual(query["hits"], ["1"])
        self.assertEqual(query["offset"], ["1"])
        self.assertEqual(timeout, probe.TIMEOUT_SECONDS)

        safe_output = json.dumps(result.to_dict(), sort_keys=True)
        for sensitive in (
            API_ID,
            AFFILIATE_ID,
            DUMMY_URL,
            "sensitive-content-id",
            "sensitive title",
        ):
            self.assertNotIn(sensitive, safe_output)

    def test_missing_affiliate_field_blocks_without_inference(self):
        result = probe.run_probe(
            env_path=self.env_path,
            fetcher=lambda *_args, **_kwargs: FakeResponse(payload(None)),
        )

        self.assertEqual(result.status, probe.BLOCKED)
        self.assertFalse(result.affiliate_link_present)
        self.assertIn("AFFILIATE_LINK_NOT_PRESENT", result.reason_codes)

    def test_unsafe_url_shapes_block_and_never_echo_value(self):
        cases = (
            ("http://al.dmm.co.jp/test", "AFFILIATE_LINK_HTTPS_REQUIRED"),
            ("https://example.invalid/test", "AFFILIATE_LINK_HOST_NOT_APPROVED"),
            (
                "https://user:password@al.dmm.co.jp/test",
                "AFFILIATE_LINK_EMBEDDED_CREDENTIALS",
            ),
        )
        for value, reason in cases:
            with self.subTest(reason=reason):
                result = probe.run_probe(
                    env_path=self.env_path,
                    fetcher=lambda *_args, **_kwargs: FakeResponse(payload(value)),
                )
                self.assertEqual(result.status, probe.BLOCKED)
                self.assertIn(reason, result.reason_codes)
                self.assertNotIn(value, json.dumps(result.to_dict()))

    def test_fanza_co_jp_is_diagnostic_only_and_remains_blocked(self):
        value = "https://al.fanza.co.jp/opaque-test"
        result = probe.run_probe(
            env_path=self.env_path,
            fetcher=lambda *_args, **_kwargs: FakeResponse(payload(value)),
        )

        self.assertEqual(result.status, probe.BLOCKED)
        self.assertFalse(result.approved_host_pass)
        self.assertTrue(result.host_matches_fanza_co_jp)
        self.assertFalse(result.host_unclassified)
        self.assertNotIn(value, json.dumps(result.to_dict()))

    def test_unknown_host_is_only_reported_as_unclassified_boolean(self):
        value = "https://unknown.example.invalid/opaque-test"
        result = probe.run_probe(
            env_path=self.env_path,
            fetcher=lambda *_args, **_kwargs: FakeResponse(payload(value)),
        )

        self.assertEqual(result.status, probe.BLOCKED)
        self.assertTrue(result.host_unclassified)
        self.assertNotIn(value, json.dumps(result.to_dict()))

    def test_missing_environment_performs_no_request(self):
        missing = Path(self.temporary.name) / "missing.env"
        calls = []

        result = probe.run_probe(
            env_path=missing,
            fetcher=lambda *_args, **_kwargs: calls.append("request"),
        )

        self.assertEqual(result.status, probe.BLOCKED)
        self.assertFalse(result.request_performed)
        self.assertEqual(calls, [])
        self.assertIn(
            "REQUIRED_ENVIRONMENT_NOT_CONFIGURED", result.reason_codes
        )

    def test_http_and_internal_errors_are_bounded(self):
        def http_error(*_args, **_kwargs):
            raise urllib.error.HTTPError(
                "https://secret.invalid", 403, "secret detail", {}, None
            )

        http_result = probe.run_probe(
            env_path=self.env_path, fetcher=http_error
        )
        self.assertEqual(http_result.status, probe.BLOCKED)
        self.assertIn("API_HTTP_ERROR", http_result.reason_codes)
        self.assertNotIn("secret", json.dumps(http_result.to_dict()))

        def internal_error(*_args, **_kwargs):
            raise RuntimeError("secret internal detail")

        internal_result = probe.run_probe(
            env_path=self.env_path, fetcher=internal_error
        )
        self.assertEqual(internal_result.status, probe.FAIL_CLOSED)
        self.assertNotIn("secret", json.dumps(internal_result.to_dict()))

    def test_cli_dry_run_is_machine_readable(self):
        output = StringIO()
        with (
            mock.patch.object(probe, "ENV_PATH", self.env_path),
            redirect_stdout(output),
        ):
            return_code = probe.main(["--dry-run"])

        self.assertEqual(return_code, 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["status"], probe.DRY_RUN_READY)
        self.assertFalse(result["request_performed"])


if __name__ == "__main__":
    unittest.main()
