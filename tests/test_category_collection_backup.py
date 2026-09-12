from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import backup_category_collection_db as backup  # noqa: E402
from tests.test_category_collection_health import database  # noqa: E402


class CategoryCollectionBackupTests(unittest.TestCase):
    def test_dry_run_creates_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.db"
            target = root / "backups"
            database(source)
            self.assertEqual(0, backup.run(source, target, dry_run=True))
            self.assertFalse(target.exists())

    def test_backup_is_created_and_revalidated(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.db"
            target = root / "backups"
            database(source)
            self.assertEqual(0, backup.run(source, target))
            files = list(target.glob("category-collection-*.db"))
            self.assertEqual(1, len(files))
            self.assertEqual(0, backup.health.assess(files[0]).database_write_performed)

    def test_missing_source_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(2, backup.run(root / "missing.db", root / "backups"))
            self.assertFalse((root / "backups").exists())


if __name__ == "__main__":
    unittest.main()
