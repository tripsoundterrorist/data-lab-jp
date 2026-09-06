from io import BytesIO
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import affiliate_link_policy as policy  # noqa: E402
import affiliate_runtime_dmm_connector as connector  # noqa: E402
import affiliate_runtime_dmm_pipeline as pipeline  # noqa: E402
import affiliate_runtime_resolution as resolution  # noqa: E402
from rights_decision_policy import CONDITIONALLY_APPROVED  # noqa: E402


CONTENT_ID = "pipeline-content-001"
DUMMY_URL = "https://fixture.fanza.co.jp/affiliate-test"


class FakeResponse(BytesIO):
    def __init__(self, payload: object, status: int = 200):
        super().__init__(json.dumps(payload).encode("utf-8"))
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class AffiliateRuntimeDmmPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.database = root / "data-lab.db"
        self.env = root / ".env"
        self.env.write_text(
            "DMM_API_ID=test-api-secret\n"
            "DMM_AFFILIATE_ID=test-affiliate-secret\n",
            encoding="utf-8",
        )
        connection = sqlite3.connect(self.database)
        connection.execute(
            "CREATE TABLE items (site TEXT, service TEXT, floor TEXT, content_id TEXT)"
        )
        connection.execute(
            "INSERT INTO items VALUES (?, ?, ?, ?)",
            ("FANZA", "digital", "videoa", CONTENT_ID),
        )
        connection.commit()
        connection.close()
        self.public_id = connector._public_item_id(
            "FANZA", "digital", "videoa", CONTENT_ID
        )

    def execute(self, **changes):
        values = {
            "pipeline_version": pipeline.PIPELINE_VERSION,
            "database_path": self.database,
            "env_path": self.env,
            "public_id": self.public_id,
            "rights_status": CONDITIONALLY_APPROVED,
            "lifecycle_status": policy.LIFECYCLE_RESOLVED,
            "verification_status": policy.VERIFICATION_PASS,
            "publication_gate_overall_eligible": True,
            "pr_disclosure_available": True,
            "emit_redirect": lambda _url: None,
            "fetcher": lambda *_args, **_kwargs: FakeResponse(
                {
                    "result": {
                        "status": 200,
                        "items": [
                            {
                                "content_id": CONTENT_ID,
                                "affiliateURL": DUMMY_URL,
                            }
                        ],
                    }
                }
            ),
        }
        values.update(changes)
        return pipeline.run_pipeline(**values)

    def test_closed_gate_stops_before_database_and_api(self):
        requests = []
        result = self.execute(
            database_path=Path(self.temporary.name) / "missing.db",
            env_path=Path(self.temporary.name) / "missing.env",
            publication_gate_overall_eligible=False,
            fetcher=lambda *_args, **_kwargs: requests.append("request"),
        )

        self.assertEqual(result.status, resolution.BLOCKED)
        self.assertFalse(result.item_lookup_attempted)
        self.assertFalse(result.api_request_attempted)
        self.assertFalse(result.delivery_attempted)
        self.assertEqual(requests, [])

    def test_future_eligible_fixture_delivers_once_in_memory(self):
        delivered = []
        before = self.database.read_bytes()

        result = self.execute(emit_redirect=delivered.append)

        self.assertEqual(result.status, resolution.DELIVERED)
        self.assertTrue(result.item_lookup_attempted)
        self.assertTrue(result.api_request_attempted)
        self.assertTrue(result.delivery_attempted)
        self.assertTrue(result.delivered)
        self.assertEqual(delivered, [DUMMY_URL])
        self.assertEqual(self.database.read_bytes(), before)
        self.assertNotIn(DUMMY_URL, json.dumps(result.to_dict()))

    def test_unapproved_api_host_never_reaches_emitter(self):
        delivered = []
        bad_url = "https://example.invalid/not-approved"

        result = self.execute(
            emit_redirect=delivered.append,
            fetcher=lambda *_args, **_kwargs: FakeResponse(
                {
                    "result": {
                        "status": 200,
                        "items": [
                            {
                                "content_id": CONTENT_ID,
                                "affiliateURL": bad_url,
                            }
                        ],
                    }
                }
            ),
        )

        self.assertEqual(result.status, resolution.BLOCKED)
        self.assertEqual(delivered, [])
        self.assertNotIn(bad_url, json.dumps(result.to_dict()))

    def test_pending_lifecycle_stops_before_callbacks(self):
        requests = []
        result = self.execute(
            lifecycle_status=policy.LIFECYCLE_PENDING,
            publication_gate_overall_eligible=False,
            fetcher=lambda *_args, **_kwargs: requests.append("request"),
        )

        self.assertEqual(result.status, resolution.BLOCKED)
        self.assertFalse(result.item_lookup_attempted)
        self.assertEqual(requests, [])

    def test_unknown_pipeline_version_fails_closed_before_callbacks(self):
        result = self.execute(pipeline_version="9")

        self.assertEqual(result.status, resolution.BLOCKED)
        self.assertFalse(result.item_lookup_attempted)
        self.assertIn("UNSUPPORTED_RESOLUTION_VERSION", result.reason_codes)


if __name__ == "__main__":
    unittest.main()
