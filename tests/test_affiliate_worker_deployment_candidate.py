from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class AffiliateWorkerDeploymentCandidateTests(unittest.TestCase):
    def setUp(self):
        self.root = ROOT / "deployment-candidates" / "affiliate-worker"
        self.config = (self.root / "wrangler.toml").read_text(encoding="utf-8")
        self.entrypoint = (self.root / "src" / "index.mjs").read_text(encoding="utf-8")

    def test_rate_limit_is_bounded_and_paid_cpu_setting_is_absent(self):
        self.assertIn('name = "AFFILIATE_CLIENT_RATE_LIMITER"', self.config)
        self.assertRegex(self.config, r"(?m)^\s*limit = 10$")
        self.assertRegex(self.config, r"(?m)^\s*period = 60$")
        self.assertNotRegex(self.config, r"(?m)^\s*cpu_ms\s*=")
        self.assertNotIn("[limits]", self.config)

    def test_candidate_has_no_route_or_observability(self):
        self.assertIn('compatibility_date = "2026-09-11"', self.config)
        self.assertIn("workers_dev = false", self.config)
        self.assertIn("preview_urls = false", self.config)
        self.assertIn("enabled = false", self.config)
        self.assertIsNone(re.search(r"(?m)^\s*routes?\s*=", self.config))

    def test_all_release_facts_are_hard_closed(self):
        for name in (
            "officialAnswerCandidate", "publicationGateEligible",
            "runtimeChainConnected", "rateLimitAllowed", "prDisclosureAvailable",
        ):
            self.assertRegex(self.entrypoint, rf"{name}: false")
        self.assertNotIn("console.", self.entrypoint)

    def test_required_worker_bindings_are_names_only_except_reviewed_d1(self):
        self.assertIn('binding = "AFFILIATE_ITEM_LOOKUP"', self.config)
        self.assertNotIn("DMM_API_ID =", self.config)
        self.assertNotIn("DMM_AFFILIATE_ID =", self.config)
        self.assertNotIn("AFFILIATE_CLIENT_KEY_SECRET =", self.config)


if __name__ == "__main__":
    unittest.main()
