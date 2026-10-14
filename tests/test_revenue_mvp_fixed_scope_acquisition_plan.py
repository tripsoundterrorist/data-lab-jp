from hashlib import sha256
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import revenue_mvp_fixed_scope_acquisition_plan as subject


def fixture(ids=range(100)):
    return "".join(f'<article class="item"><time>2026-10-01T00:00:00Z</time>'
                   f'<a href="/go/itm_{i:024x}">fixture</a></article>'
                   for i in ids).encode()


class FixedScopeAcquisitionTests(unittest.TestCase):
    def plan(self, source=None):
        source = fixture() if source is None else source
        return subject.build(source, sha256(source).hexdigest())

    def test_exact_100_private_targets_in_20_five_item_batches(self):
        plan = self.plan()
        self.assertEqual(plan.status, "OFFLINE_PLAN_READY")
        self.assertEqual((plan.target_count, plan.batch_count), (100, 20))
        self.assertTrue(all(len(batch) == 5 for batch in plan.batches))
        self.assertEqual(len(set(x for b in plan.batches for x in b)), 100)

    def test_deterministic_without_relying_on_public_order(self):
        self.assertEqual(self.plan().batches, self.plan(fixture(reversed(range(100)))).batches)

    def test_no_execution_permission_or_target_leak_in_summary(self):
        plan = self.plan()
        self.assertFalse(plan.execution_allowed)
        self.assertFalse(plan.publication_allowed)
        self.assertFalse(plan.database_write_performed)
        self.assertFalse(plan.automatic_retry_allowed)
        self.assertEqual(plan.api_calls, 0)
        self.assertNotIn("itm_", str(plan.summary()))
        self.assertNotIn("itm_", repr(plan))

    def test_hash_mismatch_rejected(self):
        self.assertEqual(subject.build(fixture(), "0" * 64).status, "BLOCKED")

    def test_incomplete_excess_duplicate_and_invalid_scope_rejected(self):
        for source in (fixture(range(99)), fixture(range(101)), fixture([0]*100),
                       fixture().replace(b"/go/", b"/other/")):
            with self.subTest(length=len(source)):
                self.assertEqual(self.plan(source).status, "BLOCKED")

    def test_rate_limit_and_unknown_stop_without_retry(self):
        for outcome in ("RATE_LIMIT", "UNCONFIRMED", "TIMEOUT", "MALFORMED"):
            self.assertTrue(subject.continuation_reason(
                outcome=outcome, source_unchanged=True).startswith("STOP_"))

    def test_unavailable_is_not_sales_end_claim(self):
        self.assertEqual(subject.continuation_reason(
            outcome="NOT_AVAILABLE", source_unchanged=True),
            "STOP_SEPARATE_TAKEDOWN_REVIEW")

    def test_changed_source_always_stops(self):
        self.assertEqual(subject.continuation_reason(
            outcome="VALID", source_unchanged=False), "STOP_SOURCE_CHANGED")

    def test_valid_structural_result_does_not_grant_execution(self):
        self.assertEqual(subject.continuation_reason(
            outcome="VALID", source_unchanged=True),
            "STRUCTURALLY_ACCEPTED_NOT_EXECUTION_PERMISSION")


if __name__ == "__main__":
    unittest.main()
