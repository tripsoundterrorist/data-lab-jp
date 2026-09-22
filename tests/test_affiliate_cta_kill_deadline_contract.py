from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import affiliate_cta_kill_deadline_contract as subject


class KillDeadlineTests(unittest.TestCase):
    def test_no_public_issuer_or_mutable_generation(self):
        self.assertEqual(subject.default_state(), subject.BLOCKED)
        with self.assertRaises(TypeError):
            subject._LifecycleLease()
        lease = subject._issue_lease_for_test(lambda: 0, 10)
        self.assertEqual(repr(lease), "<LifecycleLease>")
        for field in ("_active", "_generation", "generation", "_terminal_generation"):
            with self.assertRaises(AttributeError):
                setattr(lease, field, True)
        lease.revoke()
        lease.revoke()
        self.assertFalse(lease.valid())

    def test_invalid_times_and_clock_regression_are_terminal(self):
        for invalid in (True, False, float("nan"), float("inf"), -float("inf"), None, "0", object()):
            with self.subTest(kind=type(invalid).__name__):
                self.assertFalse(subject._issue_lease_for_test(lambda: 0, invalid).valid())
                state = [invalid]
                lease = subject._issue_lease_for_test(lambda: state[0], 10)
                self.assertFalse(lease.valid())
                state[0] = 0
                self.assertFalse(lease.valid())
        for second in (1, 10):
            state = [2]
            lease = subject._issue_lease_for_test(lambda: state[0], 10)
            self.assertTrue(lease.valid())
            state[0] = second
            self.assertFalse(lease.valid())
            state[0] = 3
            self.assertFalse(lease.valid())

    def test_revocation_during_clock_callback_is_terminal(self):
        holder = {}
        def clock():
            holder["lease"].revoke()
            return 0
        holder["lease"] = subject._issue_lease_for_test(clock, 10)
        self.assertFalse(holder["lease"].valid())


if __name__ == "__main__":
    unittest.main()
