import copy
import json
from pathlib import Path
import tempfile
import unittest

from scripts import x_aggregate_price_card as card


ROOT = Path(__file__).resolve().parents[1]


class AggregatePriceCardTests(unittest.TestCase):
    def setUp(self):
        self.value = json.loads(
            (ROOT / "docs" / "evidence" / "x-aggregate-price-candidate-20261004.json").read_text(
                encoding="utf-8"
            )
        )

    def test_preview_never_becomes_distributable(self):
        try:
            card.shared._font_path(None)
        except ValueError:
            self.skipTest("Japanese font unavailable")
        try:
            temporary_context = tempfile.TemporaryDirectory()
        except FileNotFoundError:
            self.skipTest("No writable temporary directory")
        with temporary_context as temporary:
            output = Path(temporary) / "price-card.png"
            result = card.render_price_card(self.value, output)
            self.assertEqual(result["status"], "READY_FOR_COMPLIANCE_REVIEW")
            self.assertTrue(output.is_file())
            self.assertFalse(result["distribution_allowed"])
            self.assertFalse(result["posting_performed"])
            self.assertFalse(result["upload_performed"])

    def test_bucket_mismatch_fails_closed_without_output(self):
        value = copy.deepcopy(self.value)
        value["aggregate_facts"]["under_1000"] = 34
        output = ROOT / "runtime" / "private" / "must-not-create-price-card.png"
        result = card.render_price_card(value, output)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["reason_codes"], ["PRICE_BUCKET_TOTAL_MISMATCH"])
        self.assertFalse(output.exists())

    def test_promotional_copy_fails_closed_without_output(self):
        value = copy.deepcopy(self.value)
        value["candidate_text"] = "今すぐ購入"
        output = ROOT / "runtime" / "private" / "must-not-create-promotional-card.png"
        result = card.render_price_card(value, output)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
