from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_price_filter_copy_candidate as subject
import revenue_mvp_price_display_transition as transition
from tests.revenue_mvp_historical_fixture import price_display_artifact


class PriceFilterCopyCandidateTests(unittest.TestCase):
    def setUp(self):
        cards = ''.join(
            f'<article class="item"><h2>Synthetic {i}</h2><p class="price">999円〜</p>'
            f'<time>2026-10-01T00:00:00Z</time><a href="/go/itm_{i:024x}">Fixture</a></article>'
            for i in range(100)
        )
        self.source = (
            '<meta name="robots" content="noindex,nofollow">'
            '<section><label>価格帯<select id="price-filter"></select></label>'
            '<label><select><option value="price-asc">価格が安い順</option>'
            '<option value="price-desc">価格が高い順</option>'
            '</select></label></section><div class="results-head"></div>' + cards
        ).encode()
        self.binding = patch.object(subject, "SOURCE_SHA256", sha256(self.source).hexdigest())
        self.binding.start()
        self.addCleanup(self.binding.stop)

    def test_only_exact_copy_delta_and_cards_preserved(self):
        candidate, receipt = subject.build(self.source)
        text = candidate.decode()
        self.assertEqual(subject.CARD_PATTERN.findall(text), subject.CARD_PATTERN.findall(self.source.decode()))
        for old, new in reversed(subject.REPLACEMENTS):
            self.assertEqual(text.count(new), 1)
            text = text.replace(new, old, 1)
        self.assertEqual(text.encode(), self.source)
        self.assertEqual(receipt.item_count, 100)
        self.assertTrue(receipt.card_bytes_preserved)
        self.assertNotEqual(receipt.source_sha256, receipt.candidate_sha256)

    def test_no_publication_or_verification_authority(self):
        _, receipt = subject.build(self.source)
        for key, value in asdict(receipt).items():
            if key.endswith(("allowed", "verified", "performed")):
                self.assertIs(value, False, key)

    def test_approved_wording_is_checked_independently_of_builder_constants(self):
        candidate, _ = subject.build(self.source)
        text = candidate.decode()
        self.assertIn('<label>表示価格の下限で絞り込む<select id="price-filter">', text)
        self.assertIn('<option value="price-asc">表示価格の下限が低い順</option>', text)
        self.assertIn('<option value="price-desc">表示価格の下限が高い順</option>', text)
        notice = (
            '<p class="notice" id="price-lower-bound-note">'
            '「円〜」は確認時点の最低価格です。購入金額を保証するものではありません。'
            '最新の価格・条件は公式ページでご確認ください。</p>'
        )
        self.assertEqual(text.count(notice), 1)
        self.assertIn('</section>' + notice + '<div class="results-head">', text)

    def test_missing_or_existing_new_anchors_fail_closed(self):
        for source in (
            self.source.replace(subject.REPLACEMENTS[0][0].encode(), b'<label>Unknown<select>', 1),
            self.source + subject.REPLACEMENTS[1][1].encode(),
        ):
            with patch.object(subject, "SOURCE_SHA256", sha256(source).hexdigest()):
                with self.assertRaisesRegex(ValueError, "^COPY_INSERTION_POINT_INVALID$"):
                    subject.build(source)

    def test_unknown_changed_and_already_transformed_sources_rejected(self):
        candidate, _ = subject.build(self.source)
        for source in (self.source + b"changed", self.source.replace(b"999", b"998", 1), candidate):
            with self.subTest(source_length=len(source)), self.assertRaises(ValueError):
                subject.build(source)

    def test_invalid_types_encoding_and_size_rejected(self):
        for source in (None, "html", bytearray(self.source), b"\xff", b"x" * (1024 * 1024 + 1)):
            with self.subTest(kind=type(source).__name__), self.assertRaises(ValueError):
                subject.build(source)

    def test_card_scope_and_duplicate_anchors_rejected_even_with_fixture_binding(self):
        for source in (
            self.source.replace(b'<article class="item">', b'<article>', 1),
            self.source.replace('円〜</p>'.encode(), '円</p>'.encode(), 1),
            self.source + subject.REPLACEMENTS[0][0].encode(),
        ):
            with patch.object(subject, "SOURCE_SHA256", sha256(source).hexdigest()), self.assertRaises(ValueError):
                subject.build(source)

    def test_windows_line_endings_preserved(self):
        source = self.source + b"\r\n"
        with patch.object(subject, "SOURCE_SHA256", sha256(subject._canonical(source)).hexdigest()):
            candidate, _ = subject.build(source)
        self.assertTrue(candidate.endswith(b"\r\n"))

    def test_current_source_integration_does_not_inherit_old_display_receipt(self):
        self.binding.stop()
        actual = (ROOT / "items/index.html").read_bytes()
        source = price_display_artifact(actual)
        candidate, receipt = subject.build(source)
        # Fixed output identity is a regression expectation, never publication authority.
        self.assertEqual(receipt.candidate_sha256,
                         "fcdb686092f35840cf5a9aacf6a01ac27ed269045ec4caabf5ef05809c57f39d")
        old = transition.canonical(source).replace('円〜</p>'.encode(), '円</p>'.encode())
        history = {"items_artifact_sha256": transition.BASELINE}
        self.assertEqual(transition.review(old, candidate, history).status, "BLOCKED")
        self.assertFalse(receipt.live_display_verified)
        self.assertEqual((ROOT / "items/index.html").read_bytes(), actual)
        self.assertIn(subject.NOTICE.encode(), candidate)


if __name__ == "__main__":
    unittest.main()
