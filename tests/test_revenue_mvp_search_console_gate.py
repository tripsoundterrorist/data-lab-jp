from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_search_console_gate as gate  # noqa: E402


class RevenueMvpSearchConsoleGateTests(unittest.TestCase):
    def test_current_public_shell_is_ready_but_items_remain_blocked(self):
        result = gate.run_gate()
        self.assertEqual(result.status, gate.READY)
        self.assertTrue(result.public_shell_indexing_allowed)
        self.assertFalse(result.item_indexing_allowed)
        self.assertFalse(result.search_console_write_performed)
        self.assertEqual(result.indexable_url_count, 9)
        self.assertIn("DO_NOT_REQUEST_ITEM_INDEXING", result.next_actions)

    def test_canonical_drift_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            replica = Path(temporary)
            for filename in (*gate.INDEXABLE, "sitemap.xml", "robots.txt", "404.html", "items/index.html", "items/item.html"):
                target = replica / filename
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / filename, target)
            path = replica / "about.html"
            path.write_text(path.read_text(encoding="utf-8").replace("https://datalabx.jp/about", "https://data-lab-jp.pages.dev/about"), encoding="utf-8")
            result = gate.run_gate(replica)
        self.assertEqual(result.status, gate.FAIL_CLOSED)
        self.assertFalse(result.public_shell_indexing_allowed)

    def test_item_noindex_removal_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            replica = Path(temporary)
            shutil.copytree(ROOT, replica, dirs_exist_ok=True)
            path = replica / "items/item.html"
            path.write_text(path.read_text(encoding="utf-8").replace("noindex,nofollow", "index,follow"), encoding="utf-8")
            result = gate.run_gate(replica)
        self.assertIn("PRIVATE_ROUTE_INDEXABLE", result.reason_codes)
        self.assertFalse(result.item_indexing_allowed)

    def test_cli_is_machine_readable_and_nonwriting(self):
        process = subprocess.run(
            [sys.executable, str(ROOT / "scripts/revenue_mvp_search_console_gate.py")],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        result = json.loads(process.stdout)
        self.assertEqual(result["status"], gate.READY)
        self.assertFalse(result["search_console_write_performed"])


if __name__ == "__main__":
    unittest.main()
