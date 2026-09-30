from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_expansion_collector_safety_audit as subject  # noqa: E402


COLLECTOR = ROOT / "scripts" / "collect-dmm-items.py"


class ExpansionCollectorSafetyAuditTests(unittest.TestCase):
    def test_current_collector_safety_contract_passes_without_execution(self):
        result = subject.assess(COLLECTOR)
        self.assertEqual(result.status, subject.PASS)
        self.assertEqual(result.request_interval_seconds, 1.0)
        self.assertEqual(result.timeout_seconds, 15)
        self.assertTrue(result.http_error_stops)
        self.assertTrue(result.url_error_stops)
        self.assertTrue(result.response_validation_precedes_writes)
        self.assertFalse(result.retry_loop_detected)
        self.assertEqual(result.api_calls, 0)
        self.assertEqual(result.database_writes, 0)

    def test_short_request_interval_blocks(self):
        text = COLLECTOR.read_text(encoding="utf-8").replace(
            "REQUEST_INTERVAL_SECONDS = 1.0", "REQUEST_INTERVAL_SECONDS = 0.1"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "collector.py"
            path.write_text(text, encoding="utf-8")
            result = subject.assess(path)
        self.assertIn("REQUEST_INTERVAL_UNSAFE", result.reason_codes)

    def test_retry_marker_blocks(self):
        text = COLLECTOR.read_text(encoding="utf-8") + "\nretry_count = 1\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "collector.py"
            path.write_text(text, encoding="utf-8")
            result = subject.assess(path)
        self.assertIn("RETRY_LOGIC_DETECTED", result.reason_codes)

    def test_missing_source_blocks(self):
        result = subject.assess(Path("missing.py"))
        self.assertEqual(result.status, subject.BLOCKED)


if __name__ == "__main__":
    unittest.main()
