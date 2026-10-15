from hashlib import sha256
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import revenue_mvp_price_display_transition as display
from tests.revenue_mvp_historical_fixture import historical_artifact


class HistoricalFixtureTests(unittest.TestCase):
    def setUp(self):
        self.actual=(Path(__file__).resolve().parents[1]/'items/index.html').read_bytes()
        self.baseline=historical_artifact(self.actual)
        self.candidate=self.baseline.replace((chr(0x5186)+'</p>').encode(),
            (chr(0x5186)+chr(0x301c)+'</p>').encode())

    def test_baseline_and_candidate_recover_only_exact_pinned_history(self):
        self.assertEqual(sha256(self.baseline).hexdigest(),display.BASELINE)
        self.assertEqual(sha256(self.candidate).hexdigest(),display.CANDIDATE)
        self.assertEqual(historical_artifact(self.candidate),self.baseline)
        self.assertEqual(historical_artifact(self.baseline),self.baseline)

    def test_unrelated_change_cannot_be_normalized_into_approval(self):
        for data in (self.baseline+b'other',self.candidate+b'other',b'unknown'):
            with self.assertRaises(ValueError): historical_artifact(data)

    def test_partial_price_correction_is_not_a_fixture(self):
        changed=self.baseline.replace((chr(0x5186)+'</p>').encode(),
            (chr(0x5186)+chr(0x301c)+'</p>').encode(),1)
        with self.assertRaises(ValueError): historical_artifact(changed)

    def test_windows_eol_has_same_explicit_baseline_identity(self):
        self.assertEqual(historical_artifact(self.baseline.replace(b'\n',b'\r\n')),self.baseline)
