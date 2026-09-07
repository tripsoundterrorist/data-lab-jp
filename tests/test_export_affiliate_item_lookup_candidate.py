from pathlib import Path
import json
import sqlite3
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import export_affiliate_item_lookup_candidate as exporter  # noqa: E402


class ExportAffiliateItemLookupCandidateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.database = self.root / "source.db"
        connection = sqlite3.connect(self.database)
        connection.execute(
            "CREATE TABLE items (site TEXT, service TEXT, floor TEXT, content_id TEXT)"
        )
        connection.executemany(
            "INSERT INTO items VALUES (?, ?, ?, ?)",
            [
                ("FANZA", "digital", "videoa", "content-002"),
                ("FANZA", "digital", "videoa", "content-001"),
            ],
        )
        connection.commit()
        connection.close()
        self.private = self.root / "runtime" / "private"
        self.output = self.private / "lookup.sql"

    def run_export(self, **changes):
        values = {
            "database_path": self.database,
            "output_path": self.output,
            "allowed_output_root": self.private,
        }
        values.update(changes)
        return exporter.export_candidate(**values)

    def test_exports_disabled_rows_without_mutating_source(self):
        before = self.database.read_bytes()
        result = self.run_export()
        self.assertEqual(result.status, exporter.EXPORTED)
        self.assertEqual(result.row_count, 2)
        self.assertTrue(result.all_rows_disabled)
        self.assertTrue(result.source_query_only)
        self.assertEqual(self.database.read_bytes(), before)

        target = sqlite3.connect(":memory:")
        self.addCleanup(target.close)
        target.executescript(
            (ROOT / "runtime-candidates" / "affiliate-item-lookup-schema.sql").read_text(encoding="utf-8")
        )
        target.executescript(self.output.read_text(encoding="utf-8"))
        total = target.execute("SELECT count(*) FROM affiliate_item_lookup").fetchone()[0]
        eligible = target.execute("SELECT count(*) FROM affiliate_runtime_eligible_lookup").fetchone()[0]
        self.assertEqual(total, 2)
        self.assertEqual(eligible, 0)

    def test_output_is_deterministic_and_safe_result_has_no_identifiers(self):
        result = self.run_export()
        output = json.dumps(result.to_dict(), sort_keys=True)
        self.assertNotIn("content-001", output)
        self.assertNotIn("itm_", output)
        self.assertNotIn(str(self.database), output)
        self.assertEqual(len(result.output_sha256 or ""), 64)

    def test_output_must_be_new_sql_file_directly_under_private_root(self):
        for target in (
            self.root / "outside.sql",
            self.private / "nested" / "lookup.sql",
            self.private / "lookup.txt",
        ):
            with self.subTest(target=target):
                result = self.run_export(output_path=target)
                self.assertEqual(result.status, exporter.FAIL_CLOSED)
                self.assertFalse(target.exists())
        self.private.mkdir(parents=True, exist_ok=True)
        self.output.write_text("existing", encoding="utf-8")
        result = self.run_export()
        self.assertEqual(result.status, exporter.FAIL_CLOSED)
        self.assertEqual(self.output.read_text(encoding="utf-8"), "existing")

    def test_empty_invalid_duplicate_or_unsupported_source_fails_closed(self):
        cases = (
            [],
            [("FANZA", "digital", "videoa", "bad/content")],
            [("FANZA", "digital", "videoa", "same"), ("FANZA", "digital", "videoa", "same")],
            [("DMM.com", "digital", "videoa", "content")],
        )
        for index, rows in enumerate(cases):
            with self.subTest(rows=rows):
                path = self.root / f"case-{index}.db"
                connection = sqlite3.connect(path)
                connection.execute("CREATE TABLE items (site TEXT, service TEXT, floor TEXT, content_id TEXT)")
                connection.executemany("INSERT INTO items VALUES (?, ?, ?, ?)", rows)
                connection.commit()
                connection.close()
                target = self.private / f"case-{index}.sql"
                result = self.run_export(database_path=path, output_path=target)
                self.assertEqual(result.status, exporter.FAIL_CLOSED)
                self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
