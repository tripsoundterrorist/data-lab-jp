from pathlib import Path
import hashlib
import sqlite3
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import export_revenue_mvp_expansion_lookup_candidate as subject  # noqa: E402
import validate_affiliate_item_lookup_candidate as validator  # noqa: E402


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def database(path: Path):
    connection = sqlite3.connect(path)
    connection.executescript("""
        CREATE TABLE items(id INTEGER PRIMARY KEY,site TEXT,service TEXT,floor TEXT,content_id TEXT);
        CREATE TABLE item_snapshots(id INTEGER PRIMARY KEY,item_id INTEGER,collection_run_id TEXT,source_offset INTEGER,source_position INTEGER);
        CREATE TABLE collection_runs(collection_run_id TEXT,run_type TEXT,started_at TEXT,status TEXT,max_items INTEGER,max_pages INTEGER,api_calls INTEGER,pages_fetched INTEGER,processed_items INTEGER,snapshots_inserted INTEGER,duplicate_content_ids_across_pages INTEGER);
        INSERT INTO collection_runs VALUES ('run','native','2026-10-01T00:00:00Z','success',300,6,6,6,300,300,0);
    """)
    for index in range(300):
        item_id = index + 1
        connection.execute("INSERT INTO items VALUES (?,?,?,?,?)", (item_id,"FANZA","digital","videoa",f"cid{item_id}"))
        connection.execute("INSERT INTO item_snapshots VALUES (?,?,?,?,?)", (item_id,item_id,"run",(index // 50) * 50 + 1,index % 50 + 1))
    connection.commit()
    connection.close()


class ExpansionLookupExportTests(unittest.TestCase):
    def test_exact_latest_300_exports_disabled_valid_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.db"
            output = root / "candidate.sql"
            database(source)
            result = subject.export(source, output, private_root=root, expected_database_sha256=digest(source))
            checked = validator.validate_candidate(
                output, ROOT / "runtime-candidates" / "affiliate-item-lookup-schema.sql",
                expected_sha256=result.output_sha256, expected_row_count=300,
            )
        self.assertEqual(result.status, subject.EXPORTED)
        self.assertEqual(result.row_count, 300)
        self.assertTrue(result.all_rows_disabled)
        self.assertFalse(result.d1_write_performed)
        self.assertFalse(result.publication_allowed)
        self.assertEqual(checked.status, validator.VALIDATED)
        self.assertEqual(checked.eligible_row_count, 0)

    def test_hash_mismatch_and_existing_output_block(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.db"
            output = root / "candidate.sql"
            database(source)
            self.assertEqual(subject.export(source, output, private_root=root, expected_database_sha256="0" * 64).status, subject.BLOCKED)
            output.write_text("exists", encoding="utf-8")
            self.assertEqual(subject.export(source, output, private_root=root, expected_database_sha256=digest(source)).status, subject.BLOCKED)


if __name__ == "__main__":
    unittest.main()
