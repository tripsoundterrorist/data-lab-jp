from dataclasses import replace
from pathlib import Path
import hashlib
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import temporal_filesystem_persistence_candidate as candidate  # noqa: E402
import temporal_probe_series_state_store_candidate as plans  # noqa: E402

NAME = "rank-offset000000-hits100-series-0123456789abcdef-20260910T000000000000Z.json"


def plan(document=b"{}\n", filename=NAME):
    return plans.SeriesStateWritePlan(
        plans.STORE_CANDIDATE_VERSION, plans.WRITE_PLAN_READY, True, filename,
        hashlib.sha256(document).hexdigest(), len(document), True, False, False,
        ("MEMORY_ONLY_WRITE_PLAN",))


class IsolatedPersistenceCandidateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.store = candidate.IsolatedTemporalStateStore.for_test(self.root)

    def test_atomic_write_and_exact_readback(self):
        result = self.store.persist(plan(), b"{}\n")
        self.assertEqual(result.status, "PERSISTED_AND_VERIFIED")
        self.assertTrue(result.durable)
        self.assertEqual((self.root / NAME).read_bytes(), b"{}\n")
        self.assertFalse((self.root / (NAME + ".tmp")).exists())
        self.assertFalse(result.production_write_authorized)

    def test_identical_replay_is_noop_and_collision_blocks(self):
        self.assertTrue(self.store.persist(plan(), b"{}\n").durable)
        self.assertEqual(self.store.persist(plan(), b"{}\n").status,
                         "IDENTICAL_REPLAY_NOOP")
        other = b'{"x":1}\n'
        self.assertEqual(self.store.persist(plan(other), other).reason_codes,
                         ("FILENAME_CONTENT_COLLISION",))

    def test_invalid_plan_and_document_do_not_write(self):
        for value, document in ((None, b"{}\n"), (plan(), "bad"),
                                (replace(plan(), state_write_authorized=True), b"{}\n")):
            self.assertEqual(self.store.persist(value, document).status,
                             "PERSISTENCE_BLOCKED")
        self.assertEqual(list(self.root.iterdir()), [])

    def test_frequency_limit(self):
        for index in range(4):
            name = NAME.replace("offset000000", f"offset{index:06d}")
            self.assertTrue(self.store.persist(plan(filename=name), b"{}\n").durable)
        extra = NAME.replace("offset000000", "offset000004")
        self.assertEqual(self.store.persist(plan(filename=extra), b"{}\n").reason_codes,
                         ("WRITE_FREQUENCY_LIMIT_REACHED",))

    def test_temporary_residue_requires_recovery(self):
        (self.root / (NAME + ".tmp")).write_bytes(b"partial")
        result = self.store.persist(plan(), b"{}\n")
        self.assertEqual(result.status, "RECOVERY_REQUIRED")
        self.assertEqual(result.reason_codes, ("TEMPORARY_RESIDUE_PRESENT",))


if __name__ == "__main__":
    unittest.main()
