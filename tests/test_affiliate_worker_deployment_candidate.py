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

    def test_candidate_has_exact_route_and_no_public_worker_hostname(self):
        self.assertIn('compatibility_date = "2026-09-11"', self.config)
        self.assertIn("workers_dev = false", self.config)
        self.assertIn("preview_urls = false", self.config)
        self.assertIn("enabled = false", self.config)
        self.assertIn('pattern = "datalabx.jp/go/*"', self.config)
        self.assertIn('zone_name = "datalabx.jp"', self.config)
        self.assertEqual(self.config.count('pattern = "'), 1)

    def test_release_facts_are_bound_to_the_approved_activation_scope(self):
        expected_scope = {
            "candidateSha256": "c7d569dc732b73e4085c9d860f1a54c73c201b974d37dda7ae15d9c5193dddf1",
            "artifactSha256": "c7d569dc732b73e4085c9d860f1a54c73c201b974d37dda7ae15d9c5193dddf1",
            "sourceSha256": "564bbeaf628de624e816ff8f2b4a3824119e338d3052e8d2594a084f06ef2e85",
            "publicSurface": "/items/",
            "routePrefix": "/go/",
            "maximumCtaCount": 100,
            "itemCount": 100,
            "relayOperationGuaranteed": False,
            "affiliateOutcomeGuaranteed": False,
        }
        for name, value in expected_scope.items():
            literal = str(value).lower() if isinstance(value, bool) else f'"{value}"' if isinstance(value, str) else str(value)
            self.assertIn(f"{name}: {literal}", self.entrypoint)
        for name in (
            "officialAnswerCandidate", "publicationGateEligible",
            "runtimeChainConnected", "rateLimitAllowed", "prDisclosureAvailable",
        ):
            self.assertRegex(self.entrypoint, rf"{name}: true")
        self.assertNotIn("console.", self.entrypoint)

    def test_required_worker_bindings_are_names_only_except_reviewed_d1(self):
        self.assertIn('binding = "AFFILIATE_ITEM_LOOKUP"', self.config)
        self.assertNotIn("DMM_API_ID =", self.config)
        self.assertNotIn("DMM_AFFILIATE_ID =", self.config)
        self.assertNotIn("AFFILIATE_CLIENT_KEY_SECRET =", self.config)

    def test_lifecycle_revalidation_handler_is_inert_without_a_trigger(self):
        self.assertNotIn('[triggers]', self.config)
        self.assertNotIn('crons =', self.config)
        self.assertIn("async scheduled(controller, env, ctx)", self.entrypoint)
        self.assertIn("runAffiliateLifecycleRevalidation", self.entrypoint)
        self.assertNotIn("ctx.waitUntil", self.entrypoint)


if __name__ == "__main__":
    unittest.main()
