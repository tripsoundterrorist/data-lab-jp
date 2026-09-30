import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_expansion_initial_revalidation as subject  # noqa: E402

IDS = ("itm_" + "a" * 24, "itm_" + "b" * 24)
ROWS = [{"public_id": IDS[0], "content_id": "content-a"}, {"public_id": IDS[1], "content_id": "content-b"}]


class Process:
    def __init__(self, stdout): self.stdout = stdout


def selection(): return json.dumps([{"success": True, "results": ROWS}])
def success(): return "progress\n" + json.dumps([{"success": True, "results": []}])


class InitialRevalidationTests(unittest.TestCase):
    def test_default_is_dry_and_read_only(self):
        calls = []
        result = subject.run(public_ids=IDS, runner=lambda *a, **k: (calls.append(a), Process(selection()))[1])
        self.assertEqual(result.status, "READY")
        self.assertFalse(result.database_write_performed)
        self.assertEqual(len(calls), 1)

    def test_live_requires_confirmation(self):
        result = subject.run(public_ids=IDS, execute=True, runner=lambda *a, **k: None)
        self.assertEqual(result.status, "BLOCKED")

    def test_valid_items_promote_only_after_target_and_event(self):
        calls, sql = [], []
        def runner(command, **kwargs):
            calls.append(command)
            if "--file" in command:
                sql.append(Path(command[command.index("--file") + 1]).read_text())
                return Process(success())
            return Process(selection())
        def fetcher(**kwargs):
            cid = kwargs["content_id"]
            return {"result": {"items": [{"content_id": cid, "affiliateURL": "https://example.fanza.co.jp/x/" + cid}]}}
        result = subject.run(public_ids=IDS, execute=True, confirmed=True, runner=runner,
                             fetcher=fetcher, checked_at="2026-10-01T00:00:00Z")
        self.assertEqual(result.status, "COMPLETED")
        self.assertEqual(result.valid, 2)
        self.assertTrue(result.database_write_performed)
        self.assertLess(sql[0].index("affiliate_redirect_target"), sql[0].index("affiliate_enabled=1"))
        self.assertNotIn("BEGIN TRANSACTION", sql[0])

    def test_upstream_error_stays_disabled(self):
        calls = []
        def runner(command, **kwargs):
            calls.append(command)
            return Process(selection()) if len(calls) == 1 else Process(success())
        def fail(**kwargs): raise subject.AffiliateRuntimeConnectorError("private")
        result = subject.run(public_ids=IDS, execute=True, confirmed=True, runner=runner,
                             fetcher=fail, checked_at="2026-10-01T00:00:00Z")
        self.assertEqual(result.unconfirmed, 2)
        self.assertEqual(result.valid, 0)


if __name__ == "__main__": unittest.main()
