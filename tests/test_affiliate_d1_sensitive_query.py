"""Secret-safe transport tests; all HTTP and provider calls are synthetic."""
from contextlib import redirect_stdout, redirect_stderr
import io
import json
from pathlib import Path
import sqlite3
import sys
import unittest
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import affiliate_d1_sensitive_query as subject
import revenue_mvp_expansion_initial_revalidation as initial

STAMP="2026-10-19T13:00:00Z"
ROWS=[{"public_id":"itm_"+f"{i:024x}","content_id":f"synthetic-{i}"} for i in range(5)]
URL="https://example.fanza.co.jp/synthetic?private=never-log-this"
TOKEN="synthetic-not-a-real-token"


class Response:
    def __init__(self,value,status=200): self.value=value;self.status=status
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def read(self,size): return self.value[:size]


def ack(count):
    return {"success":True,"errors":[],"result":[{"success":True,"results":[],"meta":{"changes":1}} for _ in range(count)]}


def make_client(opener,provider=lambda:TOKEN):
    return subject.D1QueryClient("a"*32,"00000000-0000-0000-0000-000000000001",provider,opener=opener)


class SensitiveQueryTests(unittest.TestCase):
    def queries(self): return subject.build_queries(ROWS,[("VALID",URL)]*5,STAMP)

    def test_one_post_with_bound_params_and_redacted_representations(self):
        queries=self.queries()
        opener=Mock(return_value=Response(json.dumps(ack(15)).encode()))
        client=make_client(opener)
        self.assertTrue(client.ready())
        with redirect_stdout(io.StringIO()) as out,redirect_stderr(io.StringIO()) as err:
            result=client.write(queries,confirmed=True)
        self.assertEqual(result.state,"APPLIED")
        self.assertEqual(opener.call_count,1)
        request=opener.call_args.args[0]
        self.assertEqual(request.method,"POST")
        self.assertTrue(request.full_url.endswith("/query"))
        self.assertNotIn("/import",request.full_url)
        body=json.loads(request.data)
        self.assertEqual(len(body["batch"]),15)
        self.assertIn(URL,body["batch"][0]["params"])
        self.assertNotIn(TOKEN,request.data.decode())
        for query in queries:
            self.assertNotIn(URL,query.sql)
            self.assertNotIn(URL,repr(query))
        self.assertNotIn(TOKEN,repr(client))
        self.assertNotIn(URL,repr(result))
        self.assertEqual(out.getvalue()+err.getvalue(),"")
        self.assertIsNone(client._token)
        self.assertEqual(client.write(queries,confirmed=True).state,"NOT_ATTEMPTED")
        self.assertEqual(opener.call_count,1)

    def test_confirmation_and_credentials_gate_before_post(self):
        for token in (None,"","bad\r\ntoken",TOKEN+" "):
            opener=Mock()
            client=make_client(opener,lambda:token)
            self.assertFalse(client.ready())
            self.assertEqual(client.write(self.queries(),confirmed=True).state,"NOT_ATTEMPTED")
            opener.assert_not_called()
        opener=Mock();client=make_client(opener);self.assertTrue(client.ready())
        self.assertEqual(client.write(self.queries()).state,"NOT_ATTEMPTED")
        opener.assert_not_called()

    def test_no_retry_and_no_secret_exception_or_response_output(self):
        for error in (TimeoutError(TOKEN+URL),RuntimeError(TOKEN+URL)):
            opener=Mock(side_effect=error);client=make_client(opener);client.ready()
            with redirect_stdout(io.StringIO()) as out,redirect_stderr(io.StringIO()) as err:
                result=client.write(self.queries(),confirmed=True)
            self.assertEqual(result.state,"UNKNOWN")
            self.assertNotIn(TOKEN+URL,str(result))
            self.assertEqual(out.getvalue()+err.getvalue(),"")
            self.assertFalse(client.ready())
            self.assertEqual(opener.call_count,1)

    def test_http_failures_and_redirects_are_uncertain_not_retried(self):
        for status in (302,401,403,429,500):
            opener=Mock(return_value=Response(b"private-response",status))
            client=make_client(opener);client.ready()
            self.assertEqual(client.write(self.queries(),confirmed=True).state,"UNKNOWN")
            self.assertEqual(opener.call_count,1)
        self.assertIsNone(subject._NoRedirect().redirect_request(None,None,302,"",{},"https://example.invalid/"))

    def test_partial_malformed_or_zero_change_responses_are_uncertain(self):
        bad=[]
        for value in (None,[],{}, {"success":False,"errors":[{"message":TOKEN+URL}]}): bad.append(json.dumps(value).encode())
        for count in (0,14,16): bad.append(json.dumps(ack(count)).encode())
        for changes in (0,2,True,None):
            value=ack(15);value["result"][0]["meta"]["changes"]=changes;bad.append(json.dumps(value).encode())
        value=ack(15);value["result"][0]["success"]=False;bad.append(json.dumps(value).encode())
        bad += [b"not-json",b"x"*262145,b"\xff"]
        for raw in bad:
            opener=Mock(return_value=Response(raw));client=make_client(opener);client.ready()
            self.assertEqual(client.write(self.queries(),confirmed=True).state,"UNKNOWN")
            self.assertEqual(opener.call_count,1)

    def test_invalid_or_reordered_batch_never_posts(self):
        good=self.queries()
        cases=[(),list(good),good*2,good[::-1],(subject.Query("DELETE FROM affiliate_item_lookup",()),),
               (subject.Query(subject.TARGET,("https://evil.invalid/",STAMP,ROWS[0]["public_id"],ROWS[0]["content_id"])),)+good[1:],
               (subject.Query(subject.TARGET,(URL,)),)+good[1:]]
        for queries in cases:
            opener=Mock();client=make_client(opener);client.ready()
            self.assertEqual(client.write(queries,confirmed=True).state,"NOT_ATTEMPTED")
            opener.assert_not_called()

    def test_sqlite_exact_outcomes_and_existing_state_guard(self):
        outcomes=[("VALID",URL),("NOT_AVAILABLE",None),("UNCONFIRMED",None),("VALID",URL),("VALID",URL)]
        queries=subject.build_queries(ROWS,outcomes,STAMP)
        with sqlite3.connect(":memory:") as db:
            db.executescript((ROOT/"runtime-candidates/affiliate-item-lookup-schema.sql").read_text(encoding="utf-8"))
            for row in ROWS:
                db.execute("INSERT INTO affiliate_item_lookup(public_id,content_id,updated_at) VALUES (?,?,?)",(row["public_id"],row["content_id"],STAMP))
            for query in queries:
                self.assertEqual(db.execute(query.sql,query.params).rowcount,1)
            self.assertEqual(db.execute("SELECT count(*) FROM affiliate_runtime_redirect_target").fetchone()[0],3)
            self.assertEqual(db.execute("SELECT count(*) FROM affiliate_lifecycle_revalidation_event").fetchone()[0],5)
            self.assertEqual(db.execute("SELECT count(*) FROM affiliate_item_lookup WHERE verification_status='FAILED' AND affiliate_enabled=0").fetchone()[0],1)
            for query in queries[:3]:
                self.assertEqual(db.execute(query.sql,query.params).rowcount,0)

    def test_builder_scope_ids_duplicates_timestamps_and_urls(self):
        for rows,outcomes,stamp in ((ROWS*2,[("VALID",URL)]*10,STAMP),(ROWS[:1]*2,[("VALID",URL)]*2,STAMP),
            (ROWS,[("VALID","http://example.fanza.co.jp/")]*5,STAMP),(ROWS,[("BAD",None)]*5,STAMP),
            (ROWS,[("VALID",URL)]*5,"not-a-date"),(ROWS,[("VALID",URL)]*5,"2026-10-19T13:00:00")):
            with self.assertRaises(ValueError): subject.build_queries(rows,outcomes,stamp)

    def test_live_without_configured_client_never_calls_provider_or_d1(self):
        provider=Mock();runner=Mock()
        result=initial.run(public_ids=tuple(r["public_id"] for r in ROWS),execute=True,confirmed=True,fetcher=provider,runner=runner)
        self.assertEqual(result.status,"BLOCKED")
        self.assertEqual(result.provider_attempts,0)
        self.assertFalse(result.database_write_performed)
        provider.assert_not_called();runner.assert_not_called()

    def test_live_confirmation_scope_and_bad_credentials_stop_before_provider(self):
        provider=Mock();runner=Mock();opener=Mock()
        ids=tuple(row["public_id"] for row in ROWS)
        for scope,confirmed in ((ids,False),(ids,1),(ids+(ids[0],),True),(ids[:1]*2,True),(('bad',),True)):
            result=initial.run(public_ids=scope,execute=True,confirmed=confirmed,fetcher=provider,
                runner=runner,query_client=make_client(opener))
            self.assertEqual(result.status,"BLOCKED")
        bad=make_client(opener,lambda:None)
        result=initial.run(public_ids=ids,execute=True,confirmed=True,fetcher=provider,runner=runner,query_client=bad)
        self.assertEqual(result.reason_codes,("SECURE_QUERY_CLIENT_REQUIRED",))
        provider.assert_not_called();runner.assert_not_called();opener.assert_not_called()

    def test_credential_exception_is_sanitized_and_old_token_cleared(self):
        getter=Mock(side_effect=[TOKEN,RuntimeError(TOKEN+URL)])
        client=make_client(Mock(),getter)
        self.assertTrue(client.ready())
        self.assertFalse(client.ready())
        self.assertIsNone(client._token)

    def test_unsafe_destination_identifiers_are_rejected(self):
        for account,database in (("evil.invalid","00000000-0000-0000-0000-000000000001"),
                                 ("a"*32,"../../evil"),("a"*32,"https://evil.invalid")):
            with self.assertRaisesRegex(ValueError,"D1_QUERY_CONFIG_INVALID"):
                subject.D1QueryClient(account,database,lambda:TOKEN,opener=Mock())

    def test_mixed_valid_and_unconfirmed_batch_is_bounded_integration(self):
        requests=[]
        def opener(request,**kwargs):
            batch=json.loads(request.data)["batch"];requests.append(batch)
            return Response(json.dumps(ack(len(batch))).encode())
        counter=0
        def provider(**kwargs):
            nonlocal counter
            counter+=1
            if counter==1: return {"result":{"items":[{"content_id":kwargs["content_id"],"affiliateURL":URL}]}}
            if counter==2: return {"result":{"items":[]}}
            return {"result":{"items":[None]}}
        runner=Mock(return_value=type("Process",(),{"stdout":json.dumps([{"success":True,"results":ROWS}])})())
        with patch("tempfile.mkstemp",side_effect=AssertionError("NO_SQL_FILE")):
            result=initial.run(public_ids=tuple(r["public_id"] for r in ROWS),execute=True,confirmed=True,
                runner=runner,fetcher=provider,query_client=make_client(opener),checked_at=STAMP)
        self.assertEqual((result.valid,result.unavailable,result.unconfirmed),(1,1,3))
        self.assertEqual(result.provider_attempts,5)
        self.assertEqual(len(requests),1)
        self.assertEqual(len(requests[0]),11)
        self.assertEqual(runner.call_count,1)

    def test_uncertain_write_is_not_reported_as_no_write(self):
        provider=Mock(side_effect=lambda **kw:{"result":{"items":[{"content_id":kw["content_id"],"affiliateURL":URL}]}})
        runner=Mock(return_value=type("Process",(),{"stdout":json.dumps([{"success":True,"results":ROWS}])})())
        opener=Mock(side_effect=TimeoutError(TOKEN+URL))
        with patch("tempfile.mkstemp",side_effect=AssertionError("NO_SQL_FILE")):
            result=initial.run(public_ids=tuple(r["public_id"] for r in ROWS),execute=True,confirmed=True,
                fetcher=provider,runner=runner,query_client=make_client(opener),checked_at=STAMP)
        self.assertIsNone(result.database_write_performed)
        self.assertEqual(result.write_outcome,"UNKNOWN")
        self.assertEqual(result.provider_attempts,5)
        self.assertEqual(provider.call_count,5)
        self.assertEqual(runner.call_count,1)
        self.assertEqual(opener.call_count,1)
        self.assertNotIn(URL,str(result.to_dict()))


if __name__=="__main__": unittest.main()
