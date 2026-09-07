from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest

from scripts.validate_affiliate_item_lookup_candidate import FAIL_CLOSED, VALIDATED, validate_candidate


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


def payload(rows: list[tuple[str, str]]) -> bytes:
    lines = ["BEGIN TRANSACTION;"]
    for public_id, content_id in rows:
        lines.append(
            "INSERT INTO affiliate_item_lookup (public_id, content_id, updated_at) VALUES "
            f"('{public_id}', '{content_id}', '1970-01-01T00:00:00Z');"
        )
    lines.append("COMMIT;")
    return ("\n".join(lines) + "\n").encode()


class ValidateAffiliateItemLookupCandidateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.schema = self.root / "schema.sql"
        self.schema.write_text(SCHEMA, encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_candidate(self, data: bytes) -> tuple[Path, str]:
        candidate = self.root / "candidate.sql"
        candidate.write_bytes(data)
        return candidate, hashlib.sha256(data).hexdigest()

    def test_valid_disabled_candidate_passes(self) -> None:
        data = payload([
            ("itm_" + "a" * 24, "abc-001"),
            ("itm_" + "b" * 24, "abc-002"),
        ])
        candidate, digest = self.write_candidate(data)
        result = validate_candidate(candidate, self.schema, expected_sha256=digest, expected_row_count=2)
        self.assertEqual(VALIDATED, result.status)
        self.assertEqual(2, result.row_count)
        self.assertTrue(result.all_rows_disabled)
        self.assertTrue(result.pending_defaults_verified)
        self.assertEqual(0, result.eligible_row_count)
        self.assertTrue(result.candidate_identity_verified)

    def test_wrong_digest_fails_before_import(self) -> None:
        data = payload([("itm_" + "a" * 24, "abc-001")])
        candidate, _ = self.write_candidate(data)
        result = validate_candidate(candidate, self.schema, expected_sha256="0" * 64, expected_row_count=1)
        self.assertEqual(FAIL_CLOSED, result.status)
        self.assertIn("CANDIDATE_IDENTITY_MISMATCH", result.reason_codes)

    def test_unexpected_statement_is_rejected(self) -> None:
        data = b"BEGIN TRANSACTION;\nDELETE FROM affiliate_item_lookup;\nCOMMIT;\n"
        candidate, digest = self.write_candidate(data)
        result = validate_candidate(candidate, self.schema, expected_sha256=digest, expected_row_count=1)
        self.assertEqual(FAIL_CLOSED, result.status)
        self.assertIn("CANDIDATE_STATEMENT_INVALID", result.reason_codes)

    def test_duplicate_identifier_is_rejected(self) -> None:
        data = payload([
            ("itm_" + "a" * 24, "abc-001"),
            ("itm_" + "a" * 24, "abc-002"),
        ])
        candidate, digest = self.write_candidate(data)
        result = validate_candidate(candidate, self.schema, expected_sha256=digest, expected_row_count=2)
        self.assertEqual(FAIL_CLOSED, result.status)
        self.assertIn("CANDIDATE_IDENTIFIER_NOT_UNIQUE", result.reason_codes)

    def test_expected_row_count_is_required(self) -> None:
        data = payload([("itm_" + "a" * 24, "abc-001")])
        candidate, digest = self.write_candidate(data)
        result = validate_candidate(candidate, self.schema, expected_sha256=digest, expected_row_count=0)
        self.assertEqual(FAIL_CLOSED, result.status)
        self.assertIn("EXPECTED_ROW_COUNT_REQUIRED", result.reason_codes)

    def test_missing_candidate_fails_closed(self) -> None:
        result = validate_candidate(
            self.root / "missing.sql",
            self.schema,
            expected_sha256="0" * 64,
            expected_row_count=1,
        )
        self.assertEqual(FAIL_CLOSED, result.status)
        self.assertIn("CANDIDATE_UNAVAILABLE", result.reason_codes)


if __name__ == "__main__":
    unittest.main()
