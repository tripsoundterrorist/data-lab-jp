from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
import json
import unittest

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import revenue_mvp_fixed_scope_offline_connection as candidate
from revenue_mvp_lifecycle_receipt import public_item_id


class ConnectionTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 26, 14, tzinfo=timezone.utc)
        pairs = sorted((public_item_id('FANZA','digital','videoa',f'fixture-{i}'), f'fixture-{i}') for i in range(100))
        self.source = ('<main>' + ''.join(
            f'<article class="item"><time>2026-09-30T00:00:00Z</time><a href="/go/{pid}">test</a></article>'
            for pid, _ in pairs) + '</main>').encode()
        self.digest = sha256(self.source).hexdigest()
        self.responses = tuple(candidate.OfflineResponse(pid, cid,
            {'result': {'status':200,'result_count':1,'total_count':1,'items':[
                {'content_id':cid,'service_code':'digital','floor_code':'videoa',
                 'affiliateURL':'https://al.fanza.co.jp/?lurl=https%3A%2F%2Fvideo.dmm.co.jp%2Fav%2F&af_id=fixture-990',
                 'prices':{'price':'100~'},'imageURL':{'large':'https://pics.dmm.co.jp/fixture.jpg'}}]}},
            200, self.now) for pid,cid in pairs[:5])

    def run_case(self, responses=None):
        return candidate.rehearse(self.source,self.digest,'a'*64,
            self.responses if responses is None else responses,batch_index=0,evaluated_at=self.now)

    def test_success_preserves_data_without_authority(self):
        receipt, data = self.run_case()
        self.assertEqual(receipt['status'], 'OFFLINE_CONNECTION_REHEARSED')
        self.assertEqual(receipt['decoded_count'],5)
        payload = json.loads(data)
        self.assertTrue(all(row['price_is_lower_bound'] for row in payload['records']))
        for name in ('trusted_acquisition_confirmed','output_written','database_write_performed','publication_allowed'):
            self.assertFalse(receipt[name])
        self.assertEqual(receipt['api_calls'],0)
        self.assertNotIn(b'affiliateURL',data)
        self.assertNotIn(b'fixture-990',data)

    def test_identity_checks_before_decoding(self):
        receipt,data = self.run_case(self.responses[:4]+(replace(self.responses[4],content_id='different'),))
        self.assertIsNone(data)
        self.assertEqual(receipt['decoded_count'],0)

    def test_partial_and_duplicate(self):
        for rows in (self.responses[:4],self.responses[:4]+self.responses[:1]):
            receipt,data=self.run_case(rows)
            self.assertIsNone(data)
            self.assertEqual(receipt['decoded_count'],0)

    def test_rate_limit_stops_without_partial_handoff(self):
        rows=self.responses[:2]+(replace(self.responses[2],http_status=429),)+self.responses[3:]
        receipt,data=self.run_case(rows)
        self.assertIsNone(data)
        self.assertEqual(receipt['reason_code'],'STOP_RATE_LIMIT')
        self.assertEqual(receipt['decoded_count'],2)

    def test_zero_match_is_review_not_sales_ended(self):
        rows=(replace(self.responses[0],payload={'result':{'status':200,'items':[],'result_count':0,'total_count':0}}),)+self.responses[1:]
        receipt,data=self.run_case(rows)
        self.assertIsNone(data)
        self.assertEqual(receipt['reason_code'],'NO_MATCH_REQUIRES_SEPARATE_REVIEW')

    def test_does_not_mutate_inputs(self):
        before=deepcopy(self.responses)
        self.run_case()
        self.assertEqual(self.responses,before)


if __name__=='__main__':
    unittest.main()
