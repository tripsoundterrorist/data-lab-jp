from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_lifecycle_receipt as lifecycle  # noqa: E402
import revenue_mvp_minimal_opaque_go_cta_activation_review as activation  # noqa: E402
import revenue_mvp_minimal_opaque_go_cta_live_integration as subject  # noqa: E402


NOW = datetime(2026, 9, 25, 8, 0, tzinfo=timezone.utc)
ARTIFACT_STAMP = "2026-09-25T07:00:06Z"
LIVE_STAMP = "2026-09-21T15:59:45Z"


def artifact(public_id):
    return (
        '<!doctype html><html><head><meta name="robots" content="noindex,nofollow"></head>'
        '<body><main><article><h1>対象商品</h1><time datetime="' + ARTIFACT_STAMP + '">' + ARTIFACT_STAMP + '</time>'
        '<aside class="affiliate-cta-block" aria-label="広告リンク">'
        '<p class="affiliate-cta-disclosure">【PR】FANZAで確認</p>'
        f'<a class="affiliate-cta-link" href="/go/{public_id}" target="_blank" '
        'rel="noopener noreferrer sponsored">確認</a>'
        '</aside></article></main></body></html>\n'
    ).encode()


def source(title="対象商品", price="100", observed=LIVE_STAMP):
    return (
        '<main><section class="item-grid">'
        f'<article class="item"><h2>{title}</h2><p class="price">{price}円</p><time>{observed}</time></article>'
        f'<article class="item"><h2>別商品</h2><p class="price">200円</p><time>{LIVE_STAMP}</time></article>'
        '</section></main>\n'
    ).encode()


class MinimalOpaqueGoCtaLiveIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "history.db"
        with sqlite3.connect(self.db) as connection:
            connection.executescript("""
                CREATE TABLE items (id INTEGER PRIMARY KEY, site TEXT, service TEXT, floor TEXT, content_id TEXT);
                CREATE TABLE item_snapshots (id INTEGER PRIMARY KEY, item_id INTEGER, observed_at TEXT, price_min INTEGER);
                CREATE TABLE item_snapshot_titles (snapshot_id INTEGER, title TEXT, observed_at TEXT);
            """)
            for index, title, price in ((1, "対象商品", 100), (2, "別商品", 200)):
                connection.execute("INSERT INTO items VALUES (?,?,?,?,?)", (index, "FIXTURE", "digital", "video", f"fixture-{index}"))
                connection.execute("INSERT INTO item_snapshots VALUES (?,?,?,?)", (index, index, LIVE_STAMP, price))
                connection.execute("INSERT INTO item_snapshot_titles VALUES (?,?,?)", (index, title, LIVE_STAMP))
        self.public_id = lifecycle.public_item_id("FIXTURE", "digital", "video", "fixture-1")
        self.artifact = artifact(self.public_id)
        self.source = source()
        self.approval = {
            "version": "0.1", "source": "CONTROL_CENTER_USER_MESSAGE", "decision": "APPROVED",
            "approved_scope": {
                "artifact_sha256": hashlib.sha256(self.artifact).hexdigest(),
                "public_route": "/items/", "cta_route_prefix": "/go/",
                "maximum_cta_count": 1, "existing_live_item_count_must_be_preserved": 2,
                "opaque_public_id_only": True, "proximate_pr_disclosure_required": True,
                "free_plan_only": True,
            },
        }
        self.approval_path = Path(self.temp.name) / "approval.json"
        self.write_approval()
        for target, field, value in (
            (subject, "SOURCE_SHA256", hashlib.sha256(self.source).hexdigest()),
            (subject, "APPROVED_ARTIFACT_SHA256", hashlib.sha256(self.artifact).hexdigest()),
            (subject, "ITEM_COUNT", 2),
            (subject, "APPROVAL_EVIDENCE_PATH", self.approval_path),
            (activation, "COMPLIANCE_APPROVED_ARTIFACT_SHA256", hashlib.sha256(self.artifact).hexdigest()),
        ):
            patcher = mock.patch.object(target, field, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def write_approval(self):
        self.approval_path.write_text(json.dumps(self.approval), encoding="utf-8")

    def build(self, live=None, approved=None):
        return subject.build_candidate(
            self.source if live is None else live,
            self.artifact if approved is None else approved,
            database=self.db, evaluated_at=NOW,
        )

    def test_one_db_bound_card_gets_only_exact_cta_diff(self):
        before = hashlib.sha256(self.db.read_bytes()).hexdigest()
        candidate, receipt = self.build()
        result = subject.preflight(
            self.source, candidate, approved_artifact=self.artifact,
            database=self.db, evaluated_at=NOW,
            expected_candidate_sha256=hashlib.sha256(candidate).hexdigest(),
            expected_item_count=2,
        )
        self.assertEqual(hashlib.sha256(self.db.read_bytes()).hexdigest(), before)
        self.assertEqual(receipt.status, subject.READY)
        self.assertEqual(result.status, subject.PASS)
        self.assertEqual((result.item_count, result.cta_count), (2, 1))
        self.assertEqual(candidate.count(b'<article class="item">'), 2)
        self.assertTrue(result.source_preserved_except_exact_cta)
        self.assertTrue(all(not getattr(result, field) for field in (
            "publication_allowed", "production_activation_allowed", "affiliate_eligibility_allowed",
            "gate_mutation_allowed", "d1_write_allowed", "deployment_allowed", "output_written",
        )))

    def test_missing_duplicate_or_existing_cta_blocks(self):
        for live in (source("missing"), source() + source(),
                     source().replace(b"</main>", b'<a href="/go/x">x</a></main>')):
            with self.subTest(length=len(live)), self.assertRaises(subject.LiveIntegrationFailure):
                self.build(live=live)

    def test_extra_card_count_blocks_after_matching_its_source_digest(self):
        live = self.source.replace(
            b"</section>",
            ('<article class="item"><h2>追加</h2><p class="price">300円</p>'
             '<time>2026-09-21T15:59:45Z</time></article></section>').encode(),
        )
        with mock.patch.object(subject, "SOURCE_SHA256", hashlib.sha256(live).hexdigest()):
            with self.assertRaisesRegex(subject.LiveIntegrationFailure, "SOURCE_ITEM_COUNT_MISMATCH"):
                self.build(live=live)

    def test_title_price_and_observation_drift_block_even_with_updated_source_digest(self):
        for live in (source(title="別名"), source(price="101"), source(observed="2026-09-21T15:59:46Z")):
            with self.subTest(length=len(live)), mock.patch.object(subject, "SOURCE_SHA256", hashlib.sha256(live).hexdigest()):
                with self.assertRaises(subject.LiveIntegrationFailure):
                    self.build(live=live)

    def test_ambiguous_history_blocks(self):
        with sqlite3.connect(self.db) as connection:
            connection.execute("INSERT INTO items VALUES (?,?,?,?,?)", (3, "FIXTURE", "digital", "video", "fixture-3"))
            connection.execute("INSERT INTO item_snapshots VALUES (?,?,?,?)", (3, 3, LIVE_STAMP, 100))
            connection.execute("INSERT INTO item_snapshot_titles VALUES (?,?,?)", (3, "対象商品", LIVE_STAMP))
        with self.assertRaisesRegex(subject.LiveIntegrationFailure, "DATABASE_CARD_BINDING_NOT_UNIQUE"):
            self.build()

    def test_duplicate_live_card_binding_blocks(self):
        live = source().replace(
            '<article class="item"><h2>別商品</h2><p class="price">200円</p>'
            f'<time>{LIVE_STAMP}</time></article>'.encode(),
            '<article class="item"><h2>対象商品</h2><p class="price">100円</p>'
            f'<time>{LIVE_STAMP}</time></article>'.encode(),
        )
        with mock.patch.object(subject, "SOURCE_SHA256", hashlib.sha256(live).hexdigest()):
            with self.assertRaisesRegex(subject.LiveIntegrationFailure, "APPROVED_PUBLIC_ID_CARD_BINDING_NOT_UNIQUE"):
                self.build(live=live)

    def test_db_digest_change_after_read_blocks(self):
        original = subject._database_digest
        calls = []

        def changed_after_read(database):
            calls.append(database)
            digest = original(database)
            return digest if len(calls) == 1 else "0" * 64

        with mock.patch.object(subject, "_database_digest", side_effect=changed_after_read):
            with self.assertRaisesRegex(subject.LiveIntegrationFailure, "DATABASE_CHANGED_DURING_BINDING"):
                self.build()
        self.assertEqual(len(calls), 2)

    def test_wrong_approved_public_id_blocks(self):
        other_id = lifecycle.public_item_id("FIXTURE", "digital", "video", "fixture-2")
        other_artifact = artifact(other_id)
        other_digest = hashlib.sha256(other_artifact).hexdigest()
        self.approval["approved_scope"]["artifact_sha256"] = other_digest
        self.write_approval()
        with mock.patch.object(subject, "APPROVED_ARTIFACT_SHA256", other_digest), \
             mock.patch.object(activation, "COMPLIANCE_APPROVED_ARTIFACT_SHA256", other_digest):
            with self.assertRaises(subject.LiveIntegrationFailure):
                self.build(approved=other_artifact)

    def test_approval_scope_source_hash_and_count_are_enforced(self):
        for key, value in (("artifact_sha256", "0" * 64), ("public_route", "/wrong/"),
                           ("cta_route_prefix", "/wrong/"), ("maximum_cta_count", 2),
                           ("existing_live_item_count_must_be_preserved", 3), ("free_plan_only", False)):
            with self.subTest(key=key):
                original = self.approval["approved_scope"][key]
                self.approval["approved_scope"][key] = value
                self.write_approval()
                with self.assertRaisesRegex(subject.LiveIntegrationFailure, "APPROVAL_SCOPE_INVALID"):
                    self.build()
                self.approval["approved_scope"][key] = original
                self.write_approval()
        with mock.patch.object(subject, "SOURCE_SHA256", "0" * 64):
            with self.assertRaises(subject.LiveIntegrationFailure):
                self.build()
        with mock.patch.object(subject, "ITEM_COUNT", 3):
            with self.assertRaises(subject.LiveIntegrationFailure):
                self.build()

    def test_preflight_rejects_changed_candidate_or_bad_digest(self):
        candidate, _ = self.build()
        for changed, digest, count in (
            (candidate.replace(b"100", b"101"), None, 2),
            (candidate, "0" * 64, 2),
            (candidate, hashlib.sha256(candidate).hexdigest(), 3),
        ):
            result = subject.preflight(
                self.source, changed, approved_artifact=self.artifact,
                database=self.db, evaluated_at=NOW,
                expected_candidate_sha256=digest or hashlib.sha256(changed).hexdigest(),
                expected_item_count=count,
            )
            self.assertEqual(result.status, subject.BLOCKED)


if __name__ == "__main__":
    unittest.main()
