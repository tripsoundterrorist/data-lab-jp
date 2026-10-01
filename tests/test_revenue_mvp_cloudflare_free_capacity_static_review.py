from pathlib import Path
import shutil
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_cloudflare_free_capacity_static_review as subject  # noqa: E402


class CloudflareFreeCapacityStaticReviewTests(unittest.TestCase):
    def test_current_static_design_is_review_ready_but_not_capacity_verified(self):
        result = subject.review()
        self.assertEqual(result.status, subject.REVIEW_READY)
        self.assertEqual(result.target_item_count, 300)
        self.assertEqual(result.cta_worker_requests_per_click, 1)
        self.assertEqual(result.cta_d1_queries_per_click, 1)
        self.assertEqual(result.lifecycle_batch_size, 5)
        self.assertTrue(result.workers_dev_disabled)
        self.assertTrue(result.preview_urls_disabled)
        self.assertFalse(result.paid_plan_required_by_static_design)
        self.assertFalse(result.cloudflare_free_plan_capacity_verified)
        self.assertTrue(result.dashboard_observation_required)
        self.assertFalse(result.activation_scope_target_ready)
        self.assertFalse(result.production_change_allowed)
        self.assertEqual(len(result.dashboard_checks), 5)

    def test_unbounded_lookup_blocks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._copy_sources(Path(directory))
            adapter = root / "runtime-candidates" / "affiliate-d1-runtime-adapter.mjs"
            adapter.write_text(
                adapter.read_text(encoding="utf-8").replace("LIMIT 2", ""),
                encoding="utf-8",
            )
            result = subject.review(root)
        self.assertEqual(result.status, subject.BLOCKED)
        self.assertIn("CTA_LOOKUP_NOT_BOUNDED", result.reason_codes)

    def test_cpu_override_blocks_free_plan_review(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._copy_sources(Path(directory))
            config = root / "deployment-candidates" / "affiliate-worker" / "wrangler.toml"
            config.write_text(
                config.read_text(encoding="utf-8") + "\n[limits]\ncpu_ms = 30\n",
                encoding="utf-8",
            )
            result = subject.review(root)
        self.assertIn("FREE_PLAN_CPU_OVERRIDE_PRESENT", result.reason_codes)

    @staticmethod
    def _copy_sources(root: Path) -> Path:
        paths = (
            Path("deployment-candidates/affiliate-worker/wrangler.toml"),
            Path("deployment-candidates/affiliate-worker/src/index.mjs"),
            Path("runtime-candidates/affiliate-d1-runtime-adapter.mjs"),
            Path("runtime-candidates/affiliate-lifecycle-revalidation.mjs"),
        )
        for relative in paths:
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, destination)
        return root


if __name__ == "__main__":
    unittest.main()
