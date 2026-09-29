from pathlib import Path
import hashlib
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_discovery_activation_candidate as candidate  # noqa: E402


def source() -> bytes:
    card = (
        '<article class="item"><div class="card-image-wrap"><img class="card-image" src="https://pics.dmm.co.jp/a.jpg" alt="架空商品" loading="lazy" decoding="async"></div>'
        '<h2>架空商品</h2><p class="price">1,200円</p><time>2026-09-21T15:59:45Z</time>'
        '<aside class="affiliate-cta-block" aria-label="広告リンク"><p>【PR】</p>'
        '<a href="/go/itm_0123456789abcdef01234567">確認</a></aside></article>'
    )
    return (
        '<!doctype html><html><head><script src="/analytics-consent.js" defer></script>'
        '<title>x</title></head><body><main id="main-content">'
        '<p id="result-count" role="status" aria-live="polite">1件</p>'
        '<p id="page-status" aria-live="polite">1 / 1</p>'
        '<section class="item-grid">' + card + '</section></main></body></html>\n'
    ).encode()


class DiscoveryActivationCandidateTests(unittest.TestCase):
    def build(self, payload=None):
        payload = payload or source()
        return candidate.build(
            payload, expected_sha256=hashlib.sha256(payload).hexdigest(),
            expected_item_count=1,
        )

    def test_preserves_entire_card_and_go_route(self):
        payload = source()
        rendered, receipt = self.build(payload)
        original_card = candidate.CARD_PATTERN.findall(payload.decode())
        self.assertEqual(candidate.CARD_PATTERN.findall(rendered.decode()), original_card)
        self.assertEqual(candidate.GO_PATTERN.findall(rendered.decode()), ["itm_0123456789abcdef01234567"])
        self.assertTrue(receipt.card_bytes_preserved)
        self.assertTrue(receipt.go_routes_preserved)
        self.assertFalse(receipt.production_write_performed)
        self.assertFalse(receipt.activation_allowed)

    def test_is_deterministic_and_adds_exact_controls_once(self):
        first, first_receipt = self.build()
        second, second_receipt = self.build()
        self.assertEqual((first, first_receipt), (second, second_receipt))
        self.assertEqual(first.count(b'discovery.js'), 1)
        self.assertEqual(first.count(b'id="item-search"'), 1)
        self.assertEqual(first.count(b'id="price-filter"'), 1)
        self.assertEqual(first.count(b'id="item-sort"'), 1)

    def test_fails_closed_on_hash_scope_duplicate_or_insertion_changes(self):
        payload = source()
        cases = [
            (payload, "0" * 64, 1),
            (payload.replace(b'class="card-image"', b'class="other"'), hashlib.sha256(payload.replace(b'class="card-image"', b'class="other"')).hexdigest(), 1),
            (payload.replace(b'1 / 1', b'changed'), hashlib.sha256(payload.replace(b'1 / 1', b'changed')).hexdigest(), 1),
            (payload.replace(b'<title>', b'<script src="discovery.js" defer></script><title>'), hashlib.sha256(payload.replace(b'<title>', b'<script src="discovery.js" defer></script><title>')).hexdigest(), 1),
        ]
        for changed, digest, count in cases:
            with self.subTest(changed=changed[:80]), self.assertRaises(candidate.CandidateFailure):
                candidate.build(changed, expected_sha256=digest, expected_item_count=count)

    def test_output_inside_repo_is_blocked(self):
        with self.assertRaises(candidate.CandidateFailure):
            candidate.write_candidate(ROOT / "candidate.html", b"x")
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "candidate.html"
            candidate.write_candidate(target, b"ok")
            self.assertEqual(target.read_bytes(), b"ok")


if __name__ == "__main__":
    unittest.main()
