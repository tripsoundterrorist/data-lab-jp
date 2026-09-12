from pathlib import Path
import hashlib
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import affiliate_d1_incremental_delta_preflight as preflight  # noqa: E402
import affiliate_d1_incremental_reconciliation as reconciliation  # noqa: E402


ROWS = [
    ("itm_aaaaaaaaaaaaaaaaaaaaaaaa", "content-a"),
    ("itm_bbbbbbbbbbbbbbbbbbbbbbbb", "content-b"),
]


def candidate(rows):
    lines = ["BEGIN TRANSACTION;"]
    lines.extend(
        "INSERT INTO affiliate_item_lookup (public_id, content_id, updated_at) "
        f"VALUES ('{public_id}', '{content_id}', '1970-01-01T00:00:00Z');"
        for public_id, content_id in rows
    )
    lines.append("COMMIT;")
    return ("\n".join(lines) + "\n").encode()


def remote(rows):
    lines = ["PRAGMA defer_foreign_keys=TRUE;"]
    lines.extend(
        'INSERT INTO "affiliate_item_lookup" '
        '("public_id","content_id","rights_status","lifecycle_status",'
        '"verification_status","affiliate_enabled","updated_at") VALUES'
        f"('{public_id}','{content_id}','PENDING_SEPARATE_POLICY',"
        "'PENDING_OFFICIAL_CONFIRMATION','PENDING',0,'1970-01-01T00:00:00Z');"
        for public_id, content_id in rows
    )
    return ("\n".join(lines) + "\n").encode()


def inputs():
    remote_bytes = remote(ROWS[:1])
    candidate_bytes = candidate(ROWS)
    result, delta = reconciliation.reconcile_snapshots(
        remote_bytes,
        candidate_bytes,
        expected_remote_sha256=hashlib.sha256(remote_bytes).hexdigest(),
        expected_candidate_sha256=hashlib.sha256(candidate_bytes).hexdigest(),
        expected_remote_row_count=1,
        expected_candidate_row_count=2,
    )
    assert result.status == reconciliation.READY and delta is not None
    schema = (ROOT / "runtime-candidates" / "affiliate-item-lookup-schema.sql").read_bytes()
    kwargs = {
        "expected_remote_sha256": hashlib.sha256(remote_bytes).hexdigest(),
        "expected_candidate_sha256": hashlib.sha256(candidate_bytes).hexdigest(),
        "expected_delta_sha256": hashlib.sha256(delta).hexdigest(),
        "expected_remote_row_count": 1,
        "expected_candidate_row_count": 2,
    }
    return remote_bytes, candidate_bytes, delta, schema, kwargs


class AffiliateD1IncrementalDeltaPreflightTests(unittest.TestCase):
    def test_exact_delta_passes_isolated_postconditions(self):
        remote_bytes, candidate_bytes, delta, schema, kwargs = inputs()
        result = preflight.assess(
            remote_bytes, candidate_bytes, delta, schema, **kwargs
        )
        self.assertEqual(result.status, preflight.READY)
        self.assertEqual((result.remote_row_count, result.delta_row_count, result.final_row_count), (1, 1, 2))
        self.assertTrue(result.all_rows_disabled)
        self.assertTrue(result.all_rows_pending)
        self.assertTrue(result.runtime_eligibility_empty)
        self.assertTrue(result.exact_delta_verified)
        self.assertTrue(result.isolated_memory_apply_verified)
        self.assertFalse(result.production_write_performed)
        self.assertFalse(result.publication_allowed)

    def test_tampered_or_wrong_identity_delta_fails_closed(self):
        remote_bytes, candidate_bytes, delta, schema, kwargs = inputs()
        cases = (
            (delta + b"\n", kwargs),
            (delta, {**kwargs, "expected_delta_sha256": "0" * 64}),
        )
        for changed, arguments in cases:
            with self.subTest(size=len(changed)):
                result = preflight.assess(
                    remote_bytes, candidate_bytes, changed, schema, **arguments
                )
                self.assertEqual(result.status, preflight.FAIL_CLOSED)
                self.assertFalse(result.production_write_performed)

    def test_non_pending_schema_fails_postcondition(self):
        remote_bytes, candidate_bytes, delta, schema, kwargs = inputs()
        changed = schema.replace(
            b"rights_status TEXT NOT NULL DEFAULT 'PENDING_SEPARATE_POLICY'",
            b"rights_status TEXT NOT NULL DEFAULT 'RESOLVED'",
        )
        result = preflight.assess(
            remote_bytes, candidate_bytes, delta, changed, **kwargs
        )
        self.assertEqual(result.status, preflight.FAIL_CLOSED)
        self.assertFalse(result.production_write_performed)


if __name__ == "__main__":
    unittest.main()
