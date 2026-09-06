from pathlib import Path
import json
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import affiliate_runtime_provider as provider  # noqa: E402


DUMMY_URL = "https://fixture.fanza.co.jp/product"


def base_arguments() -> dict:
    return {
        "provider_version": provider.PROVIDER_VERSION,
        "affiliate_url": DUMMY_URL,
        "rights_status": "CONDITIONALLY_APPROVED",
        "lifecycle_status": "RESOLVED",
        "verification_status": "PASS",
        "publication_gate_overall_eligible": True,
        "pr_disclosure_available": True,
    }


class AffiliateRuntimeProviderTests(unittest.TestCase):
    def test_closed_publication_gate_never_calls_emitter(self):
        delivered: list[str] = []
        arguments = base_arguments()
        arguments["publication_gate_overall_eligible"] = False

        result = provider.deliver_affiliate_link(
            **arguments, emit_redirect=delivered.append
        )

        self.assertEqual(result.status, provider.BLOCKED)
        self.assertFalse(result.delivery_attempted)
        self.assertFalse(result.delivered)
        self.assertEqual(delivered, [])
        self.assertIn("ADAPTER_PRODUCTION_RENDER_BLOCKED", result.reason_codes)

    def test_missing_disclosure_never_calls_emitter(self):
        delivered: list[str] = []
        arguments = base_arguments()
        arguments["pr_disclosure_available"] = False

        result = provider.deliver_affiliate_link(
            **arguments, emit_redirect=delivered.append
        )

        self.assertEqual(result.status, provider.BLOCKED)
        self.assertEqual(delivered, [])
        self.assertIn("PR_DISCLOSURE_UNAVAILABLE", result.reason_codes)

    def test_allowed_handoff_delivers_once_without_echoing_url(self):
        delivered: list[str] = []

        result = provider.deliver_affiliate_link(
            **base_arguments(), emit_redirect=delivered.append
        )

        self.assertEqual(result.status, provider.DELIVERED)
        self.assertTrue(result.delivery_attempted)
        self.assertTrue(result.delivered)
        self.assertEqual(delivered, [DUMMY_URL])
        safe_output = json.dumps(result.to_dict(), sort_keys=True)
        self.assertNotIn(DUMMY_URL, safe_output)
        self.assertNotIn("affiliate_url", safe_output.casefold())

    def test_malformed_url_never_calls_emitter_or_echoes_input(self):
        delivered: list[str] = []
        arguments = base_arguments()
        arguments["affiliate_url"] = "javascript:secret-value"

        result = provider.deliver_affiliate_link(
            **arguments, emit_redirect=delivered.append
        )

        self.assertEqual(result.status, provider.BLOCKED)
        self.assertEqual(delivered, [])
        self.assertIn("URL_SCHEME_FORBIDDEN", result.reason_codes)
        self.assertNotIn("secret-value", json.dumps(result.to_dict()))

    def test_emitter_failure_is_bounded_and_fail_closed(self):
        def failing_emitter(_url: str) -> None:
            raise RuntimeError("secret callback detail")

        result = provider.deliver_affiliate_link(
            **base_arguments(), emit_redirect=failing_emitter
        )

        self.assertEqual(result.status, provider.FAIL_CLOSED)
        self.assertTrue(result.delivery_attempted)
        self.assertFalse(result.delivered)
        self.assertEqual(result.reason_codes, ("REDIRECT_DELIVERY_FAILED",))
        self.assertNotIn("secret", json.dumps(result.to_dict()))

    def test_invalid_emitter_and_version_fail_closed(self):
        invalid_emitter = provider.deliver_affiliate_link(
            **base_arguments(), emit_redirect=None
        )
        self.assertEqual(invalid_emitter.status, provider.FAIL_CLOSED)
        self.assertIn("REDIRECT_EMITTER_INVALID", invalid_emitter.reason_codes)

        arguments = base_arguments()
        arguments["provider_version"] = "999"
        invalid_version = provider.deliver_affiliate_link(
            **arguments, emit_redirect=lambda _url: None
        )
        self.assertEqual(invalid_version.status, provider.FAIL_CLOSED)
        self.assertIn(
            "UNSUPPORTED_PROVIDER_VERSION", invalid_version.reason_codes
        )


if __name__ == "__main__":
    unittest.main()
