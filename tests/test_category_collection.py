from __future__ import annotations

import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("category_collector", ROOT / "scripts" / "collect-category-items.py")
collector = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(collector)


class CategoryCollectionTest(unittest.TestCase):
    def test_config_is_collection_only_and_unique(self):
        targets = collector.load_config()
        self.assertEqual(len(targets), 10)
        self.assertEqual(len({(x["site"], x["service"], x["floor"]) for x in targets}), 10)
        self.assertIn(("FANZA", "doujin", "digital_doujin"), {(x["site"], x["service"], x["floor"]) for x in targets})

    def test_sanitized_raw_removes_affiliate_urls_recursively(self):
        value = {
            "affiliateURL": "secret-link",
            "nested": [{"Affiliate_URL_SP": "secret-link", "api-id": "secret", "ok": 1}],
        }
        result = collector.sanitize_raw(value)
        encoded = json.dumps(result).lower()
        self.assertNotIn("affiliate", encoded)
        self.assertNotIn("api-id", encoded)
        self.assertEqual(result, {"nested": [{"ok": 1}]})

    def test_sensitive_key_matching_is_case_and_separator_insensitive(self):
        for key in ("affiliateURL", "Affiliate_URL_SP", "affiliate-id", "api_id", "AccessToken", "client_secret", "Authorization"):
            with self.subTest(key=key):
                self.assertTrue(collector.sensitive_key(key))
        for key in ("URL", "imageURL", "content_id", "title"):
            with self.subTest(key=key):
                self.assertFalse(collector.sensitive_key(key))

    def test_normalizer_preserves_roles_and_price_history_facts(self):
        item = {
            "content_id": "fixture-1", "title": "fixture", "affiliateURL": "must-disappear",
            "prices": {"price": "1,000円", "list_price": "2,000円", "deliveries": [{"type": "download"}]},
            "iteminfo": {"maker": [{"id": 1, "name": "Maker"}], "author": [{"id": 2, "name": "Author"}], "genre": [{"id": 3, "name": "Genre"}]},
        }
        result = collector.normalize(item)
        self.assertEqual(result["current_price_min"], 1000)
        self.assertEqual(result["list_price_min"], 2000)
        self.assertEqual(result["discount_amount"], 1000)
        self.assertEqual(result["discount_rate"], 50.0)
        self.assertEqual(set(result["contributors"]), {"maker", "author"})
        self.assertNotIn("affiliateURL", result["sanitized_raw"])

    def test_schema_cannot_enable_publication(self):
        connection = sqlite3.connect(":memory:")
        collector.ensure_database(connection)
        connection.execute("INSERT INTO category_sources(content_type,site,service,floor,collection_mode) VALUES('x','s','v','f','COLLECTION_ONLY')")
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute("UPDATE category_sources SET publication_allowed=1")
        connection.close()

    def test_schema_initialization_is_repeatable(self):
        connection = sqlite3.connect(":memory:")
        collector.ensure_database(connection)
        collector.ensure_database(connection)
        connection.close()

    def test_registered_source_identity_cannot_drift(self):
        connection = sqlite3.connect(":memory:")
        collector.ensure_database(connection)
        target = {"content_type": "x", "site": "s", "service": "v", "floor": "f"}
        collector.register_sources(connection, [target])
        with self.assertRaisesRegex(ValueError, "SOURCE_IDENTITY_MISMATCH"):
            collector.register_sources(connection, [{**target, "floor": "changed"}])
        connection.close()

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "category.db"
            self.assertEqual(collector.main(["--dry-run", "--database", str(database)]), 0)
            self.assertFalse(database.exists())


if __name__ == "__main__":
    unittest.main()
