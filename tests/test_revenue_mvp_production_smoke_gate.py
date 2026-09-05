from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_production_smoke_gate as gate  # noqa: E402


def html(canonical: str, *, noindex: bool = False) -> str:
    robots = '<meta name="robots" content="noindex,nofollow">' if noindex else ""
    return f'<html><head><link rel="canonical" href="{canonical}">{robots}</head></html>'


def valid_evidence():
    evidence = {
        path: gate.HttpEvidence(200, canonical, html(canonical))
        for path, canonical in gate.INDEXABLE.items()
    }
    evidence.update({
        path: gate.HttpEvidence(200, gate.ORIGIN + path, html(gate.ORIGIN + path, noindex=True))
        for path in gate.PRIVATE
    })
    evidence["/robots.txt"] = gate.HttpEvidence(
        200, gate.ORIGIN + "/robots.txt", f"User-agent: *\nSitemap: {gate.ORIGIN}/sitemap.xml\n"
    )
    urls = "".join(f"<url><loc>{url}</loc></url>" for url in gate.INDEXABLE.values())
    evidence["/sitemap.xml"] = gate.HttpEvidence(
        200, gate.ORIGIN + "/sitemap.xml",
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>',
    )
    evidence[gate.NOT_FOUND] = gate.HttpEvidence(
        404, gate.ORIGIN + gate.NOT_FOUND, html(gate.ORIGIN + "/404", noindex=True)
    )
    return evidence


class RevenueMvpProductionSmokeGateTests(unittest.TestCase):
    def test_valid_production_evidence_passes_without_unlocking_items(self):
        result = gate.validate_responses(valid_evidence())
        self.assertEqual(result.status, gate.PASS)
        self.assertFalse(result.production_write_performed)
        self.assertFalse(result.item_indexing_allowed)
        self.assertEqual(result.indexable_url_count, 9)
        self.assertEqual(result.failed_url_count, 0)
        self.assertEqual(result.failed_check_group_count, 0)

    def test_canonical_drift_fails_closed(self):
        evidence = valid_evidence()
        evidence["/about"] = gate.HttpEvidence(200, gate.ORIGIN + "/about", html("https://data-lab-jp.pages.dev/about"))
        result = gate.validate_responses(evidence)
        self.assertEqual(result.status, gate.FAIL_CLOSED)
        self.assertIn("PUBLIC_CANONICAL_MISMATCH", result.reason_codes)

    def test_item_noindex_removal_fails_closed(self):
        evidence = valid_evidence()
        evidence["/items/item"] = gate.HttpEvidence(200, gate.ORIGIN + "/items/item", html(gate.ORIGIN + "/items/item"))
        result = gate.validate_responses(evidence)
        self.assertIn("PRIVATE_ROUTE_EXPOSED_OR_UNAVAILABLE", result.reason_codes)
        self.assertFalse(result.item_indexing_allowed)

    def test_network_error_is_sanitized_and_fail_closed(self):
        def fail(_path):
            raise OSError("credential-bearing internal detail")
        result = gate.run_gate(fail)
        self.assertEqual(result.status, gate.FAIL_CLOSED)
        self.assertEqual(result.checked_url_count, 0)
        self.assertEqual(result.failed_url_count, 14)
        self.assertEqual(result.failed_check_group_count, 6)
        self.assertEqual(
            set(result.reason_codes),
            {
                "INCOMPLETE_EVIDENCE", "NOT_FOUND_ROUTE_FETCH_FAILED",
                "PRIVATE_ROUTE_FETCH_FAILED", "PUBLIC_HOME_FETCH_FAILED",
                "PUBLIC_COLUMN_FETCH_FAILED", "PUBLIC_INFORMATION_FETCH_FAILED",
                "SEO_ASSET_FETCH_FAILED", "PRODUCTION_HTTP_CHECK_FAILED",
            },
        )

    def test_one_failure_reports_only_safe_group(self):
        evidence = valid_evidence()

        def fetch(path):
            if path == "/about":
                raise TimeoutError("secret endpoint detail")
            return evidence[path]

        result = gate.run_gate(fetch)
        self.assertEqual(result.status, gate.FAIL_CLOSED)
        self.assertEqual(result.checked_url_count, 13)
        self.assertEqual(result.failed_url_count, 1)
        self.assertEqual(result.failed_check_group_count, 1)
        self.assertIn("PUBLIC_INFORMATION_FETCH_FAILED", result.reason_codes)
        self.assertNotIn("/about", str(result.to_dict()))
        self.assertNotIn("secret", str(result.to_dict()))


if __name__ == "__main__":
    unittest.main()
