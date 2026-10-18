from hashlib import sha256
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import revenue_mvp_price_display_transition as display
from tests.revenue_mvp_historical_fixture import historical_artifact
from tests.revenue_mvp_historical_fixture import price_display_artifact
import revenue_mvp_price_filter_copy_candidate as price_copy
from tests import revenue_mvp_historical_fixture as fixture


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

    def entry_copy(self):
        anchor = b'<main id="main-content">'
        self.assertEqual(self.candidate.count(anchor), 1)
        return self.candidate.replace(anchor, anchor + fixture.ENTRY_NOTICE, 1)

    def test_exact_entry_notice_recovers_test_history_without_writes(self):
        before = self.actual
        entry = self.entry_copy()
        self.assertEqual(sha256(entry).hexdigest(), fixture.ENTRY_NOTICE_SHA256)
        for data in (entry, entry.replace(b'\n', b'\r\n')):
            self.assertEqual(historical_artifact(data), self.baseline)
            self.assertEqual(price_display_artifact(data), self.candidate)
        self.assertEqual((Path(__file__).resolve().parents[1]/'items/index.html').read_bytes(), before)

    def test_changed_or_duplicate_entry_notice_is_not_test_history(self):
        entry = self.entry_copy()
        for data in (entry + b'other', entry.replace(b'/go/', b'/xx/', 1),
                     entry.replace(fixture.ENTRY_NOTICE, fixture.ENTRY_NOTICE * 2, 1),
                     entry.replace(fixture.ENTRY_NOTICE, fixture.ENTRY_NOTICE.replace(b'</p>', b'changed</p>'), 1)):
            with self.subTest(length=len(data)):
                for recover in (historical_artifact, price_display_artifact):
                    with self.assertRaises(ValueError):
                        recover(data)

    def test_entry_recovery_also_pins_source_and_exact_delta(self):
        from unittest.mock import patch
        entry = self.entry_copy()
        for data in (entry + b'other', entry.replace(fixture.ENTRY_NOTICE, fixture.ENTRY_NOTICE * 2, 1)):
            with patch.object(fixture, 'ENTRY_NOTICE_SHA256', sha256(data).hexdigest()):
                with self.assertRaises(ValueError):
                    historical_artifact(data)

    def test_entry_fixture_does_not_grant_production_authority(self):
        import revenue_mvp_current_state as state
        from unittest.mock import patch
        with patch.object(state, 'ARTIFACT_PATH') as artifact:
            artifact.read_bytes.return_value = self.entry_copy()
            result = state.current_state()
        self.assertEqual(result.status, state.FAIL_CLOSED)
        for field in ('limited_surface_live', 'edge_artifact_verified', 'cta_allowed',
                      'affiliate_integration_allowed', 'production_write_allowed'):
            self.assertFalse(getattr(result, field))

    def test_unrelated_change_cannot_be_normalized_into_approval(self):
        for data in (self.baseline+b'other',self.candidate+b'other',b'unknown'):
            with self.assertRaises(ValueError): historical_artifact(data)

    def test_partial_price_correction_is_not_a_fixture(self):
        changed=self.baseline.replace((chr(0x5186)+'</p>').encode(),
            (chr(0x5186)+chr(0x301c)+'</p>').encode(),1)
        with self.assertRaises(ValueError): historical_artifact(changed)

    def test_windows_eol_has_same_explicit_baseline_identity(self):
        self.assertEqual(historical_artifact(self.baseline.replace(b'\n',b'\r\n')),self.baseline)

    def test_exact_copy_recovers_only_explicit_test_history(self):
        copy_bytes, _ = price_copy.build(self.candidate)
        self.assertEqual(historical_artifact(copy_bytes), self.baseline)
        self.assertEqual(price_display_artifact(copy_bytes), self.candidate)
        self.assertEqual(price_display_artifact(self.candidate), self.candidate)
        self.assertEqual(historical_artifact(copy_bytes.replace(b'\n', b'\r\n')), self.baseline)

    def test_changed_or_partial_copy_cannot_become_test_history(self):
        copy_bytes, _ = price_copy.build(self.candidate)
        partial = self.candidate.decode().replace(*price_copy.REPLACEMENTS[0], 1).encode()
        for data in (copy_bytes + b'other', copy_bytes.replace(b'/go/', b'/xx/', 1), partial):
            with self.subTest(length=len(data)):
                with self.assertRaises(ValueError):
                    historical_artifact(data)
                with self.assertRaises(ValueError):
                    price_display_artifact(data)

    def test_fixture_recovery_never_makes_candidate_state_live(self):
        import revenue_mvp_current_state as state
        from unittest.mock import patch
        copy_bytes, _ = price_copy.build(self.candidate)
        self.assertEqual(historical_artifact(copy_bytes), self.baseline)
        with patch.object(state, 'ARTIFACT_PATH') as artifact:
            artifact.read_bytes.return_value = copy_bytes
            result = state.current_state()
        self.assertEqual(result.status, state.PRICE_COPY_PENDING)
        self.assertFalse(result.limited_surface_live)
        self.assertFalse(result.edge_artifact_verified)
        self.assertFalse(result.cta_allowed)
