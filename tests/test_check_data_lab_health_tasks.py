import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check-data-lab-health.py"
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("check_data_lab_health", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
subject = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(subject)


class HealthTaskCoverageTests(unittest.TestCase):
    def test_affiliate_revalidation_is_a_required_health_task(self):
        self.assertEqual(
            subject.TASK_NAMES["affiliate_revalidation"],
            "DATA LAB Daily Affiliate Revalidation",
        )
        self.assertIn(
            "DATA LAB Daily Affiliate Revalidation",
            subject.task_query_script(),
        )

    def test_unavailable_result_includes_affiliate_revalidation(self):
        tasks = subject.unavailable_tasks("access_denied")
        self.assertEqual(
            tasks["affiliate_revalidation"],
            {
                "task_name": "DATA LAB Daily Affiliate Revalidation",
                "query_status": "access_denied",
            },
        )


if __name__ == "__main__":
    unittest.main()
