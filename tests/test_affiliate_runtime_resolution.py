from pathlib import Path
import json
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import affiliate_runtime_resolution as resolution  # noqa: E402


PUBLIC_ID = "itm_" + "a" * 24
CONTENT_ID = "cid-001"
DUMMY_URL = "https://fixture.fanza.co.jp/affiliate"


def base_arguments() -> dict:
    return {
        "resolution_version": resolution.RESOLUTION_VERSION,
        "public_id": PUBLIC_ID,
        "rights_status": "CONDITIONALLY_APPROVED",
        "lifecycle_status": "RESOLVED",
        "verification_status": "PASS",
        "publication_gate_overall_eligible": True,
        "pr_disclosure_available": True,
    }


def valid_response() -> dict:
    return {
        "result": {
            "status": 200,
            "items": [{
                "content_id": CONTENT_ID,
                "affiliateURL": DUMMY_URL,
            }],
        }
    }


class AffiliateRuntimeResolutionTests(unittest.TestCase):
    def test_closed_gate_performs_no_lookup_request_or_delivery(self):
        calls: list[str] = []

        result = resolution.resolve_and_deliver_affiliate_link(
            **{
                **base_arguments(),
                "publication_gate_overall_eligible": False,
            },
            resolve_content_id=lambda _public_id: calls.append("lookup"),
            fetch_item_response=lambda _content_id: calls.append("request"),
            emit_redirect=lambda _url: calls.append("delivery"),
        )

        self.assertEqual(result.status, resolution.BLOCKED)
        self.assertFalse(result.item_lookup_attempted)
        self.assertFalse(result.api_request_attempted)
        self.assertFalse(result.delivery_attempted)
        self.assertEqual(calls, [])
        self.assertIn("PUBLICATION_GATE_CLOSED", result.reason_codes)

    def test_allowed_fixture_resolves_fetches_and_delivers_once(self):
        calls: list[tuple[str, str]] = []

        def resolve(public_id: str) -> str:
            calls.append(("lookup", public_id))
            return CONTENT_ID

        def fetch(content_id: str) -> dict:
            calls.append(("request", content_id))
            return valid_response()

        result = resolution.resolve_and_deliver_affiliate_link(
            **base_arguments(),
            resolve_content_id=resolve,
            fetch_item_response=fetch,
            emit_redirect=lambda url: calls.append(("delivery", url)),
        )

        self.assertEqual(result.status, resolution.DELIVERED)
        self.assertTrue(result.item_lookup_attempted)
        self.assertTrue(result.api_request_attempted)
        self.assertTrue(result.delivery_attempted)
        self.assertTrue(result.delivered)
        self.assertEqual(
            calls,
            [
                ("lookup", PUBLIC_ID),
                ("request", CONTENT_ID),
                ("delivery", DUMMY_URL),
            ],
        )
        safe_output = json.dumps(result.to_dict(), sort_keys=True)
        for sensitive in (PUBLIC_ID, CONTENT_ID, DUMMY_URL):
            self.assertNotIn(sensitive, safe_output)

    def test_nonmatching_api_item_never_reaches_provider(self):
        delivered: list[str] = []
        response = valid_response()
        response["result"]["items"][0]["content_id"] = "different-id"

        result = resolution.resolve_and_deliver_affiliate_link(
            **base_arguments(),
            resolve_content_id=lambda _public_id: CONTENT_ID,
            fetch_item_response=lambda _content_id: response,
            emit_redirect=delivered.append,
        )

        self.assertEqual(result.status, resolution.BLOCKED)
        self.assertFalse(result.delivery_attempted)
        self.assertEqual(delivered, [])
        self.assertIn("API_ITEM_MATCH_NOT_UNIQUE", result.reason_codes)

    def test_missing_affiliate_link_is_not_inferred(self):
        delivered: list[str] = []
        response = valid_response()
        del response["result"]["items"][0]["affiliateURL"]

        result = resolution.resolve_and_deliver_affiliate_link(
            **base_arguments(),
            resolve_content_id=lambda _public_id: CONTENT_ID,
            fetch_item_response=lambda _content_id: response,
            emit_redirect=delivered.append,
        )

        self.assertEqual(result.status, resolution.BLOCKED)
        self.assertEqual(delivered, [])
        self.assertIn("API_AFFILIATE_LINK_UNAVAILABLE", result.reason_codes)

    def test_invalid_public_id_blocks_before_callbacks(self):
        calls: list[str] = []

        result = resolution.resolve_and_deliver_affiliate_link(
            **{**base_arguments(), "public_id": "../secret"},
            resolve_content_id=lambda _public_id: calls.append("lookup"),
            fetch_item_response=lambda _content_id: calls.append("request"),
            emit_redirect=lambda _url: calls.append("delivery"),
        )

        self.assertEqual(result.status, resolution.BLOCKED)
        self.assertEqual(calls, [])
        self.assertIn("PUBLIC_ID_INVALID", result.reason_codes)
        self.assertNotIn("secret", json.dumps(result.to_dict()))

    def test_lookup_and_api_exceptions_are_bounded(self):
        def fail_lookup(_public_id: str) -> str:
            raise RuntimeError("secret lookup detail")

        lookup_result = resolution.resolve_and_deliver_affiliate_link(
            **base_arguments(),
            resolve_content_id=fail_lookup,
            fetch_item_response=lambda _content_id: valid_response(),
            emit_redirect=lambda _url: None,
        )
        self.assertEqual(lookup_result.status, resolution.FAIL_CLOSED)
        self.assertEqual(lookup_result.reason_codes, ("ITEM_RESOLUTION_FAILED",))
        self.assertNotIn("secret", json.dumps(lookup_result.to_dict()))

        def fail_request(_content_id: str) -> dict:
            raise RuntimeError("secret API detail")

        api_result = resolution.resolve_and_deliver_affiliate_link(
            **base_arguments(),
            resolve_content_id=lambda _public_id: CONTENT_ID,
            fetch_item_response=fail_request,
            emit_redirect=lambda _url: None,
        )
        self.assertEqual(api_result.status, resolution.FAIL_CLOSED)
        self.assertEqual(api_result.reason_codes, ("API_REQUEST_FAILED",))
        self.assertNotIn("secret", json.dumps(api_result.to_dict()))


if __name__ == "__main__":
    unittest.main()
