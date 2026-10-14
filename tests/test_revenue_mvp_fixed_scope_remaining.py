from unittest.mock import Mock
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import revenue_mvp_fixed_scope_remaining as subject
from tests.test_revenue_mvp_fixed_scope_first_five import FirstFiveTests


class RemainingTests(FirstFiveTests):
    def remaining(self, **overrides):
        options=dict(execute=True,confirmation=subject.CONFIRMATION)
        options.update(overrides)
        return subject.check(self.source,self.db,self.env,self.source_hash,self.db_hash,**options)

    def checker(self,*args,**kwargs):
        kwargs.update(resolver=lambda db,opaque:self.mapping[opaque],fetcher=self.fetch,
                      pause=self.waits.append,clock=lambda:self.run_clock())
        return subject.batch.check(*args,**kwargs)

    def run_clock(self):
        from datetime import datetime,timezone
        return datetime(2026,10,14,tzinfo=timezone.utc)

    def test_remaining_exact_ninety_disjoint_and_no_writes(self):
        result=self.remaining(checker=self.checker)
        plan=subject.batch.planner.build(self.source.read_bytes(),self.source_hash)
        expected={self.mapping[x] for b in plan.batches[2:] for x in b}
        self.assertEqual(set(self.calls),expected)
        self.assertEqual(len(self.calls),90)
        self.assertEqual(result['completed_batches'],18)
        self.assertEqual(result['validated_count'],90)
        self.assertFalse(result['database_write_performed'])
        self.assertEqual(subject.batch.digest(self.db),self.db_hash)

    def test_remaining_offline_and_unconfirmed_never_call_checker(self):
        checker=Mock(side_effect=AssertionError)
        self.assertEqual(self.remaining(execute=False,checker=checker)['api_calls'],0)
        self.assertEqual(self.remaining(confirmation=None,checker=checker)['api_calls'],0)
        checker.assert_not_called()

    def test_remaining_stops_first_failure_without_retry(self):
        checker=Mock(return_value={'status':'BLOCKED','reason_code':'RATE_LIMIT',
                    'api_calls':1,'validated_count':0,'lower_bound_price_count':0})
        result=self.remaining(checker=checker)
        self.assertEqual(result['api_calls'],1)
        self.assertEqual(checker.call_count,1)

    def test_remaining_stops_changed_source_after_one_batch(self):
        def progress(_): self.source.write_bytes(self.source.read_bytes()+b'changed')
        result=self.remaining(checker=self.checker,progress=progress)
        self.assertEqual(result['api_calls'],5)
        self.assertEqual(result['reason_code'],'INPUT_CHANGED')
