import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "docs/examples/revenue-mvp-ga4-product-funnel-input-v0.1.json"
RUNBOOK = ROOT / "docs/runbooks/revenue-mvp-ga4-product-funnel-review-v0.1.md"
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_product_funnel_review as review  # noqa: E402
import revenue_mvp_product_funnel_review_receipt as receipt  # noqa: E402


class Ga4ProductFunnelTemplateTests(unittest.TestCase):
    def test_template_is_waiting_not_zero_or_complete(self):
        payload = json.loads(TEMPLATE.read_text(encoding="utf-8"))
        result = review.build_review(payload)
        aggregate = receipt.build(payload)
        self.assertEqual(result.status, review.WAITING)
        self.assertIsNone(result.total_outbound_product_clicks)
        self.assertEqual(aggregate.status, receipt.BLOCKED)
        self.assertFalse(aggregate.product_funnel_review_completed)

    def test_template_and_runbook_do_not_contain_real_item_level_data(self):
        template_text = TEMPLATE.read_text(encoding="utf-8")
        runbook_text = RUNBOOK.read_text(encoding="utf-8")
        self.assertNotIn('"item_id"', template_text)
        self.assertNotIn("affiliate_url", template_text.casefold())
        self.assertIn("Keep the row-level input private", runbook_text)
        self.assertIn("never commit the GA4 export", runbook_text)


if __name__ == "__main__":
    unittest.main()
