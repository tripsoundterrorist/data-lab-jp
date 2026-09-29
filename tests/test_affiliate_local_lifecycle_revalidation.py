from pathlib import Path
import json
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import affiliate_local_lifecycle_revalidation as subject


ROWS = [
    {"public_id": "itm_" + "a" * 24, "content_id": "content-a"},
    {"public_id": "itm_" + "b" * 24, "content_id": "content-b"},
]


class Process:
    def __init__(self, returncode=0, stdout=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = "private upstream detail must not propagate"


def selection(rows=ROWS):
    return json.dumps([{"success": True, "results": rows}])


def write_success():
    return "upload progress\n" + json.dumps([{"success": True, "results": []}])


class LocalLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.files = patch.multiple(subject, ENV_PATH=ROOT / "AGENTS.md", WRANGLER_CONFIG=ROOT / "AGENTS.md")
        self.files.start()

    def tearDown(self):
        self.files.stop()

    def test_default_is_read_only_dry_run(self):
        calls = []
        options = []
        result = subject.run_cycle(runner=lambda *a, **k: (calls.append(a), options.append(k), Process(stdout=selection()))[-1])
        self.assertEqual("READY", result.status)
        self.assertEqual("DRY_RUN", result.mode)
        self.assertEqual(2, result.selected)
        self.assertFalse(result.database_write_performed)
        self.assertEqual(1, len(calls))
        self.assertEqual("utf-8", options[0]["encoding"])
        self.assertEqual("replace", options[0]["errors"])
        self.assertIn("ORDER BY affiliate_enabled ASC", subject.SELECT_SQL)

    def test_live_requires_exact_confirmation(self):
        result = subject.run_cycle(execute=True, confirmed=False, runner=lambda *a, **k: None)
        self.assertEqual("BLOCKED", result.status)
        self.assertIn("EXPLICIT_CONFIRMATION_REQUIRED", result.reason_codes)

    def test_exact_items_write_one_bounded_transaction_and_delete_temp_sql(self):
        calls = []
        sql_seen = []
        def runner(command, **kwargs):
            calls.append(command)
            if "--file" in command:
                sql_seen.append(Path(command[command.index("--file") + 1]).read_text(encoding="utf-8"))
            return Process(returncode=1, stdout=selection()) if len(calls) == 1 else Process(returncode=1, stdout=write_success())
        def connector(**kwargs):
            content_id = kwargs["content_id"]
            return {"result": {"items": [{
                "content_id": content_id,
                "affiliateURL": "https://example.fanza.co.jp/link/" + content_id,
            }]}}
        with patch.object(subject, "fetch_item_response", side_effect=connector):
            result = subject.run_cycle(execute=True, confirmed=True, runner=runner,
                                       checked_at="2026-09-29T15:00:00Z")
        self.assertEqual("COMPLETED", result.status)
        self.assertEqual(2, result.valid)
        self.assertEqual(0, result.disabled)
        self.assertTrue(result.database_write_performed)
        self.assertTrue(result.temporary_sql_deleted)
        self.assertEqual(2, len(calls))
        self.assertIn("--file", calls[1])
        self.assertNotIn("BEGIN TRANSACTION", sql_seen[0])
        self.assertNotIn("COMMIT", sql_seen[0])
        self.assertLess(sql_seen[0].index("INSERT INTO affiliate_redirect_target"),
                        sql_seen[0].index("affiliate_enabled=1"))

    def test_upstream_failure_disables_in_same_bounded_write(self):
        calls = []
        def runner(command, **kwargs):
            calls.append(command)
            return Process(stdout=selection(ROWS[:1])) if len(calls) == 1 else Process(stdout=write_success())
        with patch.object(subject, "fetch_item_response",
                          side_effect=subject.AffiliateRuntimeConnectorError("private network detail")):
            result = subject.run_cycle(execute=True, confirmed=True, runner=runner,
                                       checked_at="2026-09-29T15:00:00Z")
        self.assertEqual("COMPLETED", result.status)
        self.assertEqual(1, result.disabled)
        self.assertNotIn("private", json.dumps(result.to_dict()))

    def test_malformed_selection_fails_without_write(self):
        result = subject.run_cycle(runner=lambda *a, **k: Process(stdout="{}"))
        self.assertEqual("FAILED_SAFE", result.status)
        self.assertFalse(result.database_write_performed)

    def test_failed_d1_write_still_deletes_temporary_sql(self):
        calls = []
        def runner(command, **kwargs):
            calls.append(command)
            return Process(stdout=selection(ROWS[:1])) if len(calls) == 1 else Process(stdout="{}")
        with patch.object(subject, "fetch_item_response", return_value={
            "result": {"items": [{
                "content_id": ROWS[0]["content_id"],
                "affiliateURL": "https://example.fanza.co.jp/link/a",
            }]}
        }):
            result = subject.run_cycle(execute=True, confirmed=True, runner=runner,
                                       checked_at="2026-09-29T15:00:00Z")
        self.assertEqual("FAILED_SAFE", result.status)
        self.assertFalse(result.database_write_performed)
        self.assertTrue(result.temporary_sql_deleted)


class Response:
    status = 200
    def __init__(self, value):
        self.value = value
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self):
        return json.dumps(self.value).encode()


def urllib_content_id(url):
    from urllib.parse import parse_qs, urlsplit
    return parse_qs(urlsplit(url).query)["cid"][0]


if __name__ == "__main__":
    unittest.main()
