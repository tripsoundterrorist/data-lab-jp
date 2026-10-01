import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import affiliate_public_route_health as subject


def html(count=100):
    return "".join(
        f'<a href="/go/itm_{value:024x}">item</a>' for value in range(count)
    )


class AffiliatePublicRouteHealthTests(unittest.TestCase):
    def test_exact_100_routes_are_healthy_and_output_is_aggregate_only(self):
        result = subject.run(
            fetch_items=lambda: (200, html()),
            probe=lambda _path: (302, subject.EXPECTED_DESTINATION_HOST),
        )
        self.assertEqual("HEALTHY", result.status)
        self.assertEqual(100, result.published_cta_count)
        self.assertEqual(100, result.redirect_http_302_count)
        self.assertEqual(0, result.redirect_failure_count)
        rendered = json.dumps(result.to_dict())
        self.assertNotIn("itm_", rendered)
        self.assertNotIn("/go/", rendered)
        self.assertFalse(result.external_write_performed)

    def test_one_bad_status_fails_closed(self):
        calls = 0
        def probe(_path):
            nonlocal calls
            calls += 1
            return (404, None) if calls == 1 else (302, subject.EXPECTED_DESTINATION_HOST)
        result = subject.run(fetch_items=lambda: (200, html()), probe=probe)
        self.assertEqual("FAILED_SAFE", result.status)
        self.assertEqual(99, result.redirect_http_302_count)
        self.assertEqual(1, result.redirect_failure_count)

    def test_wrong_destination_host_fails_closed(self):
        result = subject.run(
            fetch_items=lambda: (200, html()),
            probe=lambda _path: (302, "example.invalid"),
        )
        self.assertEqual("FAILED_SAFE", result.status)
        self.assertEqual(100, result.redirect_failure_count)
        self.assertFalse(result.destination_host_verified)

    def test_missing_duplicate_or_unavailable_items_page_fails_closed(self):
        for response in ((200, html(99)), (503, html())):
            with self.subTest(response=response[0:1]):
                result = subject.run(fetch_items=lambda value=response: value)
                self.assertEqual("FAILED_SAFE", result.status)
                self.assertEqual(0, result.published_cta_count)
        duplicate = html(99) + '<a href="/go/itm_000000000000000000000000">again</a>'
        result = subject.run(fetch_items=lambda: (200, duplicate))
        self.assertEqual("FAILED_SAFE", result.status)


if __name__ == "__main__":
    unittest.main()
