from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import category_collection_health as health  # noqa: E402
import ebook_comic_review_pair_impact_audit as subject  # noqa: E402


SCHEMA = ROOT / "db" / "category-collection-schema.sql"
CONFIG = ROOT / "config" / "category-collection-v0.1.json"


def build_database(path: Path) -> None:
    now = datetime.now(timezone.utc).isoformat()
    connection = sqlite3.connect(path)
    connection.executescript(SCHEMA.read_text(encoding="utf-8"))
    connection.execute(
        "INSERT INTO category_sources(source_id,content_type,site,service,floor,collection_mode) "
        "VALUES(1,'ebook_comic','FANZA','ebook','comic','COLLECTION_ONLY')"
    )
    connection.execute(
        "INSERT INTO category_collection_runs(run_id,source_id,started_at,finished_at,status,source_sort,requested_hits,fetched_items,response_sha256) "
        "VALUES('run-1',1,?,?,'success','date',3,3,?)",
        (now, now, "0" * 64),
    )
    for item_id, pair in enumerate(((4.0, 3), (None, None), (None, 2)), start=1):
        connection.execute(
            "INSERT INTO category_items(item_id,source_id,content_id,title,item_url,image_json,contributors_json,series_json,genre_json,source_extension_json,first_observed_at,last_observed_at,normalizer_version) "
            "VALUES(?,1,?,?,?, '{}','{}','[]','[]','{}',?,?,'0.1')",
            (item_id, f"fixture-{item_id}", "Title", "https://example.invalid/item", now, now),
        )
        connection.execute(
            "INSERT INTO category_item_snapshots(item_id,run_id,observed_at,review_average,review_count,source_sort,source_position,sanitized_raw_json) "
            "VALUES(?,'run-1',?,?,?,'date',?,'{}')",
            (item_id, now, pair[0], pair[1], item_id),
        )
    connection.commit()
    connection.close()


class EbookComicReviewPairImpactAuditTests(unittest.TestCase):
    def test_reports_only_aggregate_states_and_never_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "category.db"
            build_database(database)
            with mock.patch.object(
                subject.health,
                "assess",
                return_value=mock.Mock(status=health.HEALTHY),
            ):
                result = subject.assess(database, CONFIG)
        self.assertEqual(result.status, subject.READY)
        self.assertEqual(result.item_count, 3)
        self.assertEqual(result.complete_pair_count, 1)
        self.assertEqual(result.absent_pair_count, 1)
        self.assertEqual(result.incomplete_pair_count, 1)
        self.assertEqual(result.invalid_pair_count, 0)
        self.assertEqual(result.omission_candidate_count, 2)
        self.assertFalse(result.artifact_created)
        self.assertFalse(result.database_write_performed)
        self.assertFalse(result.source_history_mutation_allowed)
        self.assertFalse(result.publication_allowed)
        rendered = str(result.to_dict())
        self.assertNotIn("fixture", rendered)
        self.assertNotIn("Title", rendered)

    def test_invalid_policy_decision_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "category.db"
            build_database(database)
            invalid = mock.Mock(status=subject.policy.FAIL_CLOSED, source_state="INVALID")
            with mock.patch.object(
                subject.health,
                "assess",
                return_value=mock.Mock(status=health.HEALTHY),
            ), mock.patch.object(subject.policy, "assess", return_value=invalid):
                result = subject.assess(database, CONFIG)
        self.assertEqual(result.status, subject.FAIL_CLOSED)
        self.assertEqual(result.invalid_pair_count, 3)
        self.assertFalse(result.publication_allowed)

    def test_unhealthy_collection_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(
                subject.health,
                "assess",
                return_value=mock.Mock(status=health.FAIL_CLOSED),
            ):
                result = subject.assess(Path(directory) / "missing.db", CONFIG)
        self.assertEqual(result.status, subject.FAIL_CLOSED)
        self.assertEqual(result.item_count, 0)
        self.assertFalse(result.publication_allowed)


if __name__ == "__main__":
    unittest.main()
