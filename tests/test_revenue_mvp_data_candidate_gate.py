from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_data_candidate_gate as gate  # noqa: E402


PUBLIC_ID = "itm_0123456789abcdef01234567"
STAMP = "2026-09-04T00:00:00Z"


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def confidence(detailed=False):
    value = {
        "score": 80,
        "label": {"code": "HIGH", "en": "High", "ja": "高"},
        "version": "0.1",
    }
    if detailed:
        value.update({
            "components": {
                "freshness": 80, "observation_depth": 80,
                "metadata_completeness": 80, "price_data": 80,
                "temporal_confidence": 80,
            },
            "warnings": [],
        })
    return value


def price(detailed=False):
    value = {
        "version": "0.1", "observed_set_percentile": None,
        "percentile_method": "midrank", "price_band": None,
    }
    if detailed:
        value.update({
            "genre_comparisons": [],
            "maker_comparison": {"available": False, "comparisons": []},
            "price_history": {
                "first_observed_price": 1000,
                "first_price_observed_at": STAMP,
                "latest_observed_price": 1000,
                "latest_price_observed_at": STAMP,
                "min_observed_price": 1000,
                "max_observed_price": 1000,
                "price_observation_count": 1,
                "distinct_price_observation_dates": 1,
                "price_observation_span_days": 0,
            },
            "warnings": [],
        })
    return value


def detail_digest(files):
    digest = sha256()
    for path in sorted(key for key in files if key.startswith("items/")):
        digest.update(path.encode())
        digest.update(b"\0")
        digest.update(files[path])
    return digest.hexdigest()


def candidate_files():
    index_item = {
        "public_id": PUBLIC_ID, "title": "Fixture", "image_url": None,
        "current_price": 1000, "data_confidence": confidence(),
        "price_analysis": price(), "last_observed_at": STAMP,
    }
    detail_item = {
        **index_item, "item_url": None,
        "metadata": {"maker": [], "series": [], "actress": [], "genre": []},
        "price_observed_at": STAMP,
        "data_confidence": confidence(True), "price_analysis": price(True),
    }
    index = {
        "public_schema_version": "0.1", "generated_at": STAMP,
        "as_of": STAMP, "items": [index_item],
    }
    detail = {
        "public_schema_version": "0.1", "generated_at": STAMP,
        "as_of": STAMP, "item": detail_item,
    }
    path = f"items/01/{PUBLIC_ID}.json"
    files = {"index.json": encoded(index), path: encoded(detail)}
    manifest = {
        "public_schema_version": "0.1", "public_policy_version": "0.1",
        "generated_at": STAMP, "as_of": STAMP, "item_count": 1,
        "data_confidence_version": "0.1", "price_analysis_version": "0.1",
        "publication_status": "local_validation_only",
        "rights_review_required": [
            "title", "image_url", "item_url", "maker", "series", "actress", "genre",
        ],
        "price_analysis_scope": "current_data_lab_observed_set",
        "price_analysis_caveats": [], "index_path": "index.json",
        "item_detail_pattern": "items/{shard}/{public_id}.json",
        "index_sha256": sha256(files["index.json"]).hexdigest(),
        "detail_aggregate_sha256": detail_digest(files),
    }
    files["manifest.json"] = encoded(manifest)
    return files


def ready_audit():
    return SimpleNamespace(
        status="READY", database_present=True, database_size_bytes=1024,
        items_count=1, item_snapshots_count=2, collection_runs_count=1,
        reason_codes=("DB_BASELINE_READY",),
    )


class RevenueMvpDataCandidateGateTests(unittest.TestCase):
    def run_ready(self, build):
        with mock.patch.object(gate, "audit_database", return_value=ready_audit()):
            return gate.run_gate(
                Path("ignored.db"), as_of=gate._timestamp(STAMP),
                generated_at=gate._timestamp(STAMP), build_documents=build,
            )

    def test_valid_candidate_is_validated_but_never_publishable(self):
        result = self.run_ready(lambda *_: (candidate_files(), {}))
        self.assertEqual(result.status, gate.LOCAL_CANDIDATE_VALIDATED)
        self.assertEqual(result.artifact_validation, "PASS")
        self.assertEqual(result.candidate_item_count, 1)
        self.assertEqual(result.candidate_shard_count, 1)
        self.assertEqual(result.rights_gate, "PASS")
        self.assertEqual(result.lifecycle_gate, "PENDING_OFFICIAL_CONFIRMATION")
        self.assertEqual(result.semantics_gate, "PENDING_OFFICIAL_CONFIRMATION")
        self.assertFalse(result.publication_allowed)

    def test_database_block_stops_before_candidate_build(self):
        audit = ready_audit()
        audit.status = "BLOCKED"
        audit.reason_codes = ("INTEGRITY_CHECK_FAILED",)
        build = mock.Mock()
        with mock.patch.object(gate, "audit_database", return_value=audit):
            result = gate.run_gate(
                Path("ignored.db"), as_of=gate._timestamp(STAMP),
                generated_at=gate._timestamp(STAMP), build_documents=build,
            )
        build.assert_not_called()
        self.assertEqual(result.status, gate.BLOCKED)
        self.assertEqual(result.artifact_validation, "NOT_RUN")

    def test_invalid_artifact_fails_closed(self):
        result = self.run_ready(lambda *_: ({"manifest.json": b"{"}, {}))
        self.assertEqual(result.status, gate.BLOCKED)
        self.assertEqual(result.artifact_validation, "FAIL_CLOSED")
        self.assertIn("ARTIFACT_VALIDATION_FAILED", result.reason_codes)
        self.assertFalse(result.publication_allowed)

    def test_builder_exception_is_redacted(self):
        def exploding(*_):
            raise RuntimeError("secret/path/product title")

        result = self.run_ready(exploding)
        serialized = json.dumps(result.to_dict())
        self.assertEqual(result.status, gate.FAIL_CLOSED)
        self.assertEqual(result.reason_codes, ("CANDIDATE_BUILD_FAILED",))
        self.assertNotIn("secret/path/product title", serialized)

    def test_safe_result_excludes_candidate_payload(self):
        result = self.run_ready(lambda *_: (candidate_files(), {}))
        serialized = json.dumps(result.to_dict())
        self.assertNotIn("Fixture", serialized)
        self.assertNotIn(PUBLIC_ID, serialized)
        self.assertNotIn("http", serialized)

    def test_cli_missing_database_is_blocked(self):
        missing = ROOT / "data" / "not-present.db"
        process = subprocess.run(
            [sys.executable, str(ROOT / "scripts/revenue_mvp_data_candidate_gate.py"),
             "--db", str(missing)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(process.returncode, 2)
        self.assertIn('"status": "BLOCKED"', process.stdout)
        self.assertNotIn(str(missing), process.stdout)


if __name__ == "__main__":
    unittest.main()
