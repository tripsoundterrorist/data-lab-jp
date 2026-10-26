from datetime import datetime, timedelta, timezone
from hashlib import sha256
import hmac
import json
from pathlib import Path
import re
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import revenue_mvp_fixed_scope_candidate as subject
import revenue_mvp_fixed_scope_handoff as handoff
from revenue_mvp_fixed_scope_refresh_review import Observation
from revenue_mvp_fixed_scope_response_review import DecodeResult


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,10,27,1,tzinfo=timezone.utc)
        self.key=b'synthetic-archive-key-only-0000000'
        self.source=(
            '<html><head><meta name="robots" content="noindex"><link rel="canonical" href="https://example.test/items/"></head>'
            '<body><h1>Fixture</h1><script>/* unchanged synthetic consent */</script><main>'+''.join(
            f'<article class="item"><div class="card-image-wrap"><img class="card-image" src="https://pics.dmm.co.jp/old.jpg" alt="Title {i}" loading="lazy"></div><h2>Title {i}</h2><p class="price">999円〜</p><time>2020-01-01T00:00:00Z</time><aside>PR<a href="/go/itm_{i:024x}" rel="sponsored">official</a></aside></article>'
            for i in range(100))+'</main><footer>unchanged</footer></body></html>').encode()
        self.dbhash='a'*64
        self.archives=self.fixtures(self.source)

    def fixtures(self,source,stamp=None):
        stamp=stamp or self.now-timedelta(minutes=1)
        result=[]
        for batch in range(20):
            rows=tuple(DecodeResult('STRUCTURAL_OBSERVATION_READY','FIXTURE',
                Observation(f'itm_{i:024x}',stamp,100+i,'https://pics.dmm.co.jp/new.jpg',
                            stamp,stamp,stamp,'VALID'),bool(i%2)) for i in range(batch*5,batch*5+5))
            receipt,data=handoff.build(source,sha256(source).hexdigest(),self.dbhash,rows,
                batch_index=batch,evaluated_at=self.now)
            self.assertIsNotNone(data)
            payload=dict(version=subject.archive.VERSION,handoff=json.loads(data))
            signature=hmac.new(self.key,subject.archive.DOMAIN+subject.archive._json(payload),'sha256').hexdigest()
            result.append(subject.archive._json(dict(payload=payload,authentication=signature)))
        return tuple(result)

    def aggregate(self,archives=None,source=None,**changes):
        source=self.source if source is None else source
        args=dict(expected_source_sha256=sha256(source).hexdigest(),expected_database_sha256=self.dbhash,
                  authentication_key=self.key,evaluated_at=self.now)
        args.update(changes)
        return subject.aggregate(self.archives if archives is None else archives,source,**args)

    def test_complete_preserves_scope_title_links_dates_and_shell(self):
        receipt,verified=self.aggregate()
        self.assertEqual(receipt['record_count'],100)
        result,candidate,sidecar=subject.build_candidate(verified,self.source,evaluated_at=self.now)
        self.assertEqual(result['status'],'OFFLINE_FIXED_HUNDRED_CANDIDATE_READY')
        self.assertEqual(result['added_count'],0); self.assertEqual(result['removed_count'],0)
        self.assertEqual(re.findall(rb'href="[^"]*"',candidate),re.findall(rb'href="[^"]*"',self.source))
        self.assertEqual(re.findall(rb'<h2>.*?</h2>',candidate),re.findall(rb'<h2>.*?</h2>',self.source))
        self.assertEqual(re.findall(rb'<time>.*?</time>',candidate),re.findall(rb'<time>.*?</time>',self.source))
        self.assertIn('<p class="price">100円</p>'.encode(),candidate)
        self.assertIn('<p class="price">101円〜</p>'.encode(),candidate)
        self.assertEqual(candidate.count(b'https://pics.dmm.co.jp/new.jpg'),100)
        self.assertEqual(candidate.split(b'<article')[0],self.source.split(b'<article')[0])
        self.assertEqual(candidate.split(b'</main>')[1],self.source.split(b'</main>')[1])
        meta=json.loads(sidecar)
        self.assertEqual(len(meta['records']),100)
        self.assertFalse(meta['title_freshness_renewed'])
        self.assertFalse(meta['publication_allowed'])
        self.assertEqual(meta['candidate_sha256'],sha256(candidate).hexdigest())

    def test_missing_extra_duplicate_and_wrong_key(self):
        for archives in (self.archives[:19],self.archives+self.archives[:1],self.archives[:19]+self.archives[:1]):
            receipt,verified=self.aggregate(archives)
            self.assertIsNone(verified)
        self.assertIsNone(self.aggregate(authentication_key=b'x'*32)[1])

    def test_reordered_batches_are_deterministic(self):
        _,a=self.aggregate()
        _,b=self.aggregate(tuple(reversed(self.archives)))
        self.assertEqual(subject.build_candidate(a,self.source,evaluated_at=self.now),
                         subject.build_candidate(b,self.source,evaluated_at=self.now))

    def test_mixed_database_and_source_refused(self):
        self.assertIsNone(self.aggregate(expected_database_sha256='b'*64)[1])
        self.assertIsNone(self.aggregate(source=self.source+b' ')[1])

    def test_archive_tamper_stops(self):
        changed=self.archives[0].replace(b'"price":100',b'"price":99',1)
        self.assertIsNone(self.aggregate((changed,)+self.archives[1:])[1])

    def test_stale_and_future_archive_sets_refused(self):
        for now in (self.now+timedelta(hours=25),self.now-timedelta(minutes=2),self.now.replace(tzinfo=None)):
            self.assertIsNone(self.aggregate(evaluated_at=now)[1])

    def test_owned_set_cannot_be_forged(self):
        _,original=self.aggregate()
        forged=subject.ArchiveSet(original.source_sha256,original.database_sha256,original._records)
        receipt,data,sidecar=subject.build_candidate(forged,self.source,evaluated_at=self.now)
        self.assertIsNone(data); self.assertIsNone(sidecar)
        self.assertEqual(receipt['reason_code'],'OWNED_VERIFIED_ARCHIVE_SET_REQUIRED')

    def test_build_rechecks_source_and_freshness(self):
        _,verified=self.aggregate()
        self.assertIsNone(subject.build_candidate(verified,self.source+b' ',evaluated_at=self.now)[1])
        self.assertIsNone(subject.build_candidate(verified,self.source,evaluated_at=self.now+timedelta(hours=25))[1])

    def test_layout_or_missing_image_shape_does_not_fallback(self):
        for source in (self.source.replace(b'class="card-image"',b'class="other-image"',1),
                       self.source.replace(b'class="price"',b'class="other-price"',1)):
            archives=self.fixtures(source)
            _,verified=self.aggregate(archives,source)
            receipt,data,sidecar=subject.build_candidate(verified,source,evaluated_at=self.now)
            self.assertIsNone(data); self.assertIsNone(sidecar)

    def test_no_execution_or_publication_authority(self):
        receipt,verified=self.aggregate()
        result,_,_=subject.build_candidate(verified,self.source,evaluated_at=self.now)
        for item in (receipt,result):
            for field in ('publication_allowed','database_write_performed','output_written','key_read_performed'):
                self.assertFalse(item[field])
            self.assertEqual(item['api_calls'],0)


if __name__=='__main__':
    unittest.main()
