from pathlib import Path
import sqlite3
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "runtime-candidates" / "affiliate-item-lookup-schema.sql"
PUBLIC_ID = "itm_0123456789abcdef01234567"
CONTENT_ID = "lookup-content-001"
STAMP = "2026-09-07T00:00:00Z"


class AffiliateItemLookupSchemaTests(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.addCleanup(self.connection.close)
        self.connection.executescript(SCHEMA.read_text(encoding="utf-8"))

    def insert(self, **changes):
        values = {
            "public_id": PUBLIC_ID,
            "content_id": CONTENT_ID,
            "rights_status": "PENDING_SEPARATE_POLICY",
            "lifecycle_status": "PENDING_OFFICIAL_CONFIRMATION",
            "verification_status": "PENDING",
            "affiliate_enabled": 0,
            "updated_at": STAMP,
        }
        values.update(changes)
        self.connection.execute(
            """
            INSERT INTO affiliate_item_lookup (
                public_id, content_id, rights_status, lifecycle_status,
                verification_status, affiliate_enabled, updated_at
            ) VALUES (
                :public_id, :content_id, :rights_status, :lifecycle_status,
                :verification_status, :affiliate_enabled, :updated_at
            )
            """,
            values,
        )

    def eligible_rows(self):
        return self.connection.execute(
            "SELECT public_id, content_id FROM affiliate_runtime_eligible_lookup"
        ).fetchall()

    def test_schema_contains_no_item_rows(self):
        count = self.connection.execute(
            "SELECT count(*) FROM affiliate_item_lookup"
        ).fetchone()[0]
        self.assertEqual(count, 0)

    def test_default_pending_row_is_not_runtime_visible(self):
        self.connection.execute(
            "INSERT INTO affiliate_item_lookup (public_id, content_id, updated_at) VALUES (?, ?, ?)",
            (PUBLIC_ID, CONTENT_ID, STAMP),
        )
        self.assertEqual(self.eligible_rows(), [])

    def test_only_explicitly_complete_row_is_runtime_visible(self):
        self.insert(
            rights_status="CONDITIONALLY_APPROVED",
            lifecycle_status="RESOLVED",
            verification_status="PASS",
            affiliate_enabled=1,
        )
        self.assertEqual(self.eligible_rows(), [(PUBLIC_ID, CONTENT_ID)])

    def test_enabled_row_cannot_bypass_each_required_status(self):
        changes = (
            {"rights_status": "PENDING_SEPARATE_POLICY", "lifecycle_status": "RESOLVED", "verification_status": "PASS"},
            {"rights_status": "CONDITIONALLY_APPROVED", "lifecycle_status": "PENDING_OFFICIAL_CONFIRMATION", "verification_status": "PASS"},
            {"rights_status": "CONDITIONALLY_APPROVED", "lifecycle_status": "RESOLVED", "verification_status": "PENDING"},
        )
        for index, values in enumerate(changes):
            with self.subTest(values=values):
                with self.assertRaises(sqlite3.IntegrityError):
                    self.insert(
                        public_id=f"itm_{index:024x}",
                        content_id=f"content-{index}",
                        affiliate_enabled=1,
                        **values,
                    )

    def test_identifier_constraints_reject_malformed_values(self):
        for index, values in enumerate((
            {"public_id": "../secret"},
            {"public_id": "itm_0123456789ABCDEF01234567"},
            {"public_id": "itm_0123456789abcdef0123456g"},
            {"content_id": "bad/content"},
            {"content_id": ""},
        )):
            with self.subTest(values=values):
                with self.assertRaises(sqlite3.IntegrityError):
                    self.insert(
                        public_id=values.get("public_id", f"itm_{index:024x}"),
                        content_id=values.get("content_id", f"content-{index}"),
                    )

    def test_duplicate_public_or_content_identifier_is_rejected(self):
        self.insert()
        for values in (
            {"public_id": PUBLIC_ID, "content_id": "other-content"},
            {"public_id": "itm_ffffffffffffffffffffffff", "content_id": CONTENT_ID},
        ):
            with self.subTest(values=values):
                with self.assertRaises(sqlite3.IntegrityError):
                    self.insert(**values)

    def test_schema_has_no_secret_or_affiliate_url_columns(self):
        columns = {
            row[1] for row in self.connection.execute(
                "PRAGMA table_info(affiliate_item_lookup)"
            )
        }
        self.assertNotIn("api_id", columns)
        self.assertNotIn("affiliate_id", columns)
        self.assertNotIn("affiliate_url", columns)
        self.assertNotIn("affiliateURL", columns)


if __name__ == "__main__":
    unittest.main()
