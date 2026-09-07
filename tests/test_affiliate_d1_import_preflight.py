from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest

from scripts.affiliate_d1_import_preflight import (
    FAIL_CLOSED,
    PREFLIGHT_READY,
    preflight_d1_import,
)


SCHEMA = """CREATE TABLE affiliate_item_lookup (
    public_id TEXT PRIMARY KEY,
    content_id TEXT NOT NULL UNIQUE,
    rights_status TEXT NOT NULL DEFAULT 'PENDING_SEPARATE_POLICY',
    lifecycle_status TEXT NOT NULL DEFAULT 'PENDING_OFFICIAL_CONFIRMATION',
    verification_status TEXT NOT NULL DEFAULT 'PENDING',
    affiliate_enabled INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
) STRICT;
CREATE VIEW affiliate_runtime_eligible_lookup AS
SELECT public_id, content_id FROM affiliate_item_lookup
WHERE affiliate_enabled = 1
  AND rights_status = 'CONDITIONALLY_APPROVED'
  AND lifecycle_status = 'RESOLVED'
  AND verification_status = 'PASS';
"""


def candidate_payload() -> bytes:
    return (
        "BEGIN TRANSACTION;\n"
        "INSERT INTO affiliate_item_lookup (public_id, content_id, updated_at) VALUES "
        "('itm_0123456789abcdef01234567', 'abc-123', '1970-01-01T00:00:00Z');\n"
        "COMMIT;\n"
    ).encode("utf-8")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class AffiliateD1ImportPreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.schema = root / "schema.sql"
        self.candidate = root / "candidate.sql"
        self.schema.write_text(SCHEMA, encoding="utf-8")
        self.payload = candidate_payload()
        self.candidate.write_bytes(self.payload)
        self.schema_sha = hashlib.sha256(SCHEMA.encode("utf-8")).hexdigest()
        self.candidate_sha = digest(self.payload)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_preflight(self, **overrides):
        args = {
            "candidate_path": self.candidate,
            "schema_path": self.schema,
            "expected_candidate_sha256": self.candidate_sha,
            "expected_schema_sha256": self.schema_sha,
            "expected_row_count": 1,
        }
        args.update(overrides)
        return preflight_d1_import(**args)

    def test_ready_evidence_never_authorizes_or_performs_import(self) -> None:
        result = self.run_preflight()
        self.assertEqual(result.status, PREFLIGHT_READY)
        self.assertEqual(result.row_count, 1)
        self.assertTrue(result.schema_identity_verified)
        self.assertTrue(result.candidate_identity_verified)
        self.assertTrue(result.all_rows_disabled)
        self.assertTrue(result.pending_defaults_verified)
        self.assertEqual(result.eligible_row_count, 0)
        self.assertFalse(result.d1_import_allowed)
        self.assertFalse(result.cloudflare_write_performed)
        self.assertIn("MANUAL_CLOUDFLARE_STEP_REQUIRED", result.reason_codes)

    def test_schema_identity_mismatch_fails_closed(self) -> None:
        result = self.run_preflight(expected_schema_sha256="0" * 64)
        self.assertEqual(result.status, FAIL_CLOSED)
        self.assertEqual(result.reason_codes, ("SCHEMA_IDENTITY_MISMATCH",))
        self.assertFalse(result.d1_import_allowed)
        self.assertFalse(result.cloudflare_write_performed)

    def test_candidate_identity_mismatch_fails_closed(self) -> None:
        result = self.run_preflight(expected_candidate_sha256="0" * 64)
        self.assertEqual(result.status, FAIL_CLOSED)
        self.assertEqual(result.reason_codes, ("CANDIDATE_IDENTITY_MISMATCH",))
        self.assertTrue(result.schema_identity_verified)
        self.assertFalse(result.candidate_identity_verified)

    def test_row_count_mismatch_is_rejected_by_private_validator(self) -> None:
        result = self.run_preflight(expected_row_count=2)
        self.assertEqual(result.status, FAIL_CLOSED)
        self.assertEqual(result.reason_codes, ("PRIVATE_ARTIFACT_VALIDATION_FAILED",))
        self.assertTrue(result.schema_identity_verified)
        self.assertTrue(result.candidate_identity_verified)

    def test_schema_that_enables_rows_is_rejected_even_when_identity_matches(self) -> None:
        unsafe_schema = SCHEMA.replace("DEFAULT 0", "DEFAULT 1")
        self.schema.write_text(unsafe_schema, encoding="utf-8")
        result = self.run_preflight(
            expected_schema_sha256=hashlib.sha256(unsafe_schema.encode("utf-8")).hexdigest()
        )
        self.assertEqual(result.status, FAIL_CLOSED)
        self.assertEqual(result.reason_codes, ("PRIVATE_ARTIFACT_VALIDATION_FAILED",))
        self.assertFalse(result.d1_import_allowed)

    def test_invalid_expected_hash_shape_fails_before_validation(self) -> None:
        result = self.run_preflight(expected_candidate_sha256="not-a-sha")
        self.assertEqual(result.status, FAIL_CLOSED)
        self.assertEqual(result.reason_codes, ("EXPECTED_CANDIDATE_SHA256_REQUIRED",))


if __name__ == "__main__":
    unittest.main()
