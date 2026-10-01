import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import product_image_public_health as subject


def html(count=100):
    return "".join(
        f'<img class="card-image" src="https://pics.dmm.co.jp/a/{value:03d}.jpg">'
        for value in range(count)
    )


class ProductImagePublicHealthTests(unittest.TestCase):
    def test_exact_100_images_are_healthy_and_output_is_aggregate_only(self):
        result = subject.run(
            fetch_items=lambda: (200, html()),
            probe=lambda _url: (200, "image/jpeg"),
        )
        self.assertEqual("HEALTHY", result.status)
        self.assertEqual(100, result.published_image_count)
        self.assertEqual(100, result.healthy_image_count)
        self.assertEqual(0, result.image_failure_count)
        rendered = json.dumps(result.to_dict())
        self.assertNotIn("pics.dmm", rendered)
        self.assertNotIn(".jpg", rendered)
        self.assertFalse(result.external_write_performed)

    def test_one_bad_response_fails_closed(self):
        calls = 0

        def probe(_url):
            nonlocal calls
            calls += 1
            return (404, "text/html") if calls == 1 else (200, "image/jpeg")

        result = subject.run(fetch_items=lambda: (200, html()), probe=probe)
        self.assertEqual("FAILED_SAFE", result.status)
        self.assertEqual(99, result.healthy_image_count)
        self.assertEqual(1, result.image_failure_count)

    def test_non_image_content_type_fails_closed(self):
        result = subject.run(
            fetch_items=lambda: (200, html()),
            probe=lambda _url: (200, "text/html"),
        )
        self.assertEqual("FAILED_SAFE", result.status)
        self.assertEqual(100, result.image_failure_count)

    def test_count_duplicate_host_query_and_items_fail_closed(self):
        cases = [
            (200, html(99)),
            (503, html()),
            (200, html(99) + '<img class="card-image" src="https://pics.dmm.co.jp/a/000.jpg">'),
            (200, html(99) + '<img class="card-image" src="https://example.invalid/a.jpg">'),
            (200, html(99) + '<img class="card-image" src="https://pics.dmm.co.jp/a.jpg?token=x">'),
        ]
        for response in cases:
            with self.subTest(status=response[0]):
                result = subject.run(fetch_items=lambda value=response: value)
                self.assertEqual("FAILED_SAFE", result.status)
                self.assertEqual(0, result.published_image_count)


if __name__ == "__main__":
    unittest.main()
