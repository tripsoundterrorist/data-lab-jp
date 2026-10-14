from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import revenue_mvp_fixed_scope_first_five as subject
from revenue_mvp_lifecycle_receipt import public_item_id


class FirstFiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.source, self.db, self.env = root/"source.html", root/"db", root/"env"
        self.mapping = {public_item_id("FANZA", "digital", "videoa", f"fixture-{i:03}"):
                        f"fixture-{i:03}" for i in range(100)}
        self.source.write_text("".join(
            f'<article class="item"><time>2026-10-01T00:00:00Z</time>'
            f'<a href="/go/{opaque}">fixture</a></article>' for opaque in self.mapping),
            encoding="utf-8")
        self.db.write_bytes(b"fixture database")
        self.env.write_text("fixture only", encoding="utf-8")
        self.source_hash, self.db_hash = subject.digest(self.source), subject.digest(self.db)
        self.calls = []
        self.waits = []

    def fetch(self, *, content_id, env_path):
        self.calls.append(content_id)
        return {"result": {"status": 200, "result_count": 1, "total_count": 1,
                "items": [{"content_id": content_id, "service_code": "digital",
                "floor_code": "videoa", "affiliateURL": "https://al.fanza.co.jp/?fixture=1",
                "prices": {"price": "1000~"},
                "imageURL": {"large": "https://pics.dmm.co.jp/fixture.jpg"}}]}}

    def run_check(self, **overrides):
        options = dict(execute=True, confirmation=subject.CONFIRMATION,
            resolver=lambda db, opaque: self.mapping[opaque],
            fetcher=self.fetch, pause=self.waits.append,
            clock=lambda: datetime(2026,10,14,tzinfo=timezone.utc))
        options.update(overrides)
        return subject.check(self.source,self.db,self.env,self.source_hash,self.db_hash,**options)

    def test_exact_five_no_write_or_private_output(self):
        result = self.run_check()
        self.assertEqual(result["status"],"FIVE_ITEM_READ_ONLY_CHECK_COMPLETE")
        self.assertEqual((result["api_calls"],result["validated_count"]),(5,5))
        self.assertEqual(len(self.calls),5)
        self.assertEqual(self.waits,[1.0]*4)
        for field in ("database_write_performed","d1_write_performed",
                      "publication_allowed","scheduler_changed","raw_payload_persisted"):
            self.assertFalse(result[field])
        self.assertNotIn("fixture-",str(result))
        self.assertNotIn("https://",str(result))
        self.assertEqual(subject.digest(self.db),self.db_hash)

    def test_default_offline_no_requests(self):
        result=self.run_check(execute=False)
        self.assertEqual(result["api_calls"],0)
        self.assertFalse(self.calls)

    def test_confirmation_missing_no_requests(self):
        self.assertEqual(self.run_check(confirmation=None)["api_calls"],0)

    def test_identity_unresolved_before_requests(self):
        self.assertEqual(self.run_check(resolver=lambda *args:None)["api_calls"],0)

    def test_identity_mismatch_before_requests(self):
        self.assertEqual(self.run_check(resolver=lambda *args:"other")["api_calls"],0)

    def test_changed_source_or_db_rejected(self):
        for path in (self.source,self.db):
            original=path.read_bytes()
            path.write_bytes(original+b"changed")
            self.assertEqual(self.run_check()["api_calls"],0)
            path.write_bytes(original)

    def test_rate_limit_zero_result_malformed_and_exception_stop_first(self):
        for payload in ({"result":{"status":429}},
                        {"result":{"status":200,"result_count":0,"total_count":0,"items":[]}},
                        {}):
            result=self.run_check(fetcher=lambda **kwargs:payload)
            self.assertEqual(result["api_calls"],1)
            self.assertEqual(result["validated_count"],0)
        def fail(**kwargs):
            raise RuntimeError("private error must not leak")
        result=self.run_check(fetcher=fail)
        self.assertEqual(result["api_calls"],1)
        self.assertNotIn("private error",str(result))

    def test_sidecar_stops_before_requests(self):
        Path(str(self.db)+"-wal").write_bytes(b"fixture")
        self.assertEqual(self.run_check()["api_calls"],0)

    def test_second_five_exact_disjoint_selection(self):
        first = self.run_check()
        first_ids = set(self.calls)
        self.calls.clear()
        second = self.run_check(batch_index=1,confirmation=subject.SECOND_CONFIRMATION)
        plan = subject.planner.build(self.source.read_bytes(),self.source_hash)
        self.assertEqual(set(self.calls),{self.mapping[x] for x in plan.batches[1]})
        self.assertFalse(first_ids.intersection(self.calls))
        self.assertEqual((second["api_calls"],second["validated_count"]),(5,5))
        self.assertEqual(second["batch_index"],1)
        self.assertEqual(first["batch_index"],0)

    def test_confirmation_is_batch_specific(self):
        self.assertEqual(self.run_check(batch_index=1)["api_calls"],0)
        self.assertEqual(self.run_check(confirmation=subject.SECOND_CONFIRMATION)["api_calls"],0)

    def test_other_batch_scope_and_bool_rejected(self):
        for index in (-1,20,True,"1"):
            self.assertEqual(self.run_check(batch_index=index)["api_calls"],0)

    def test_second_five_offline_and_exception_do_not_retry(self):
        self.assertEqual(self.run_check(batch_index=1,execute=False)["api_calls"],0)
        result=self.run_check(batch_index=1,confirmation=subject.SECOND_CONFIRMATION,
                              fetcher=lambda **kwargs:{"result":{"status":429}})
        self.assertEqual(result["api_calls"],1)
        self.assertEqual(result["validated_count"],0)


if __name__=="__main__":
    unittest.main()
