from io import BytesIO
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
import urllib.parse


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "affiliate_runtime_dmm_connector.py"
SPEC = importlib.util.spec_from_file_location(
    "affiliate_runtime_dmm_connector", SCRIPT
)
connector = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = connector
SPEC.loader.exec_module(connector)


API_ID = "test-api-secret"
AFFILIATE_ID = "test-affiliate-secret"
CONTENT_ID = "test-content-001"
AFFILIATE_URL = "https://al.fanza.co.jp/opaque-test"


class FakeResponse(BytesIO):
    def __init__(self, payload: object, status: int = 200):
        super().__init__(json.dumps(payload).encode("utf-8"))
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class AffiliateRuntimeDmmConnectorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.database = root / "data-lab.db"
        self.env = root / ".env"
        self.env.write_text(
            f"DMM_API_ID={API_ID}\nDMM_AFFILIATE_ID={AFFILIATE_ID}\n",
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

    def test_resolves_public_id_from_query_only_database(self):
        before = self.database.read_bytes()

        resolved = connector.resolve_content_id(self.database, self.public_id)

        self.assertEqual(resolved, CONTENT_ID)
        self.assertEqual(self.database.read_bytes(), before)

    def test_unknown_or_invalid_public_id_returns_none(self):
        self.assertIsNone(
            connector.resolve_content_id(
                self.database, "itm_" + ("0" * 24)
            )
        )
        self.assertIsNone(
            connector.resolve_content_id(self.database, "invalid")
        )

    def test_fetches_exactly_one_item_without_persistence_or_output(self):
        requests = []
        payload = {
            "result": {
                "status": 200,
                "items": [
                    {
                        "content_id": CONTENT_ID,
                        "affiliateURL": AFFILIATE_URL,
                    }
                ],
            }
        }

        def fetcher(request, timeout):
            requests.append((request, timeout))
            return FakeResponse(payload)

        result = connector.fetch_item_response(
            content_id=CONTENT_ID,
            env_path=self.env,
            fetcher=fetcher,
        )

        self.assertEqual(result, payload)
        self.assertEqual(len(requests), 1)
        request, timeout = requests[0]
        query = urllib.parse.parse_qs(
            urllib.parse.urlsplit(request.full_url).query
        )
        self.assertEqual(query["cid"], [CONTENT_ID])
        self.assertEqual(query["hits"], ["1"])
        self.assertEqual(query["offset"], ["1"])
        self.assertEqual(timeout, connector.TIMEOUT_SECONDS)
        self.assertFalse(any(self.database.parent.glob("*.json")))

    def test_missing_environment_fails_with_bounded_code(self):
        missing = self.database.parent / "missing.env"
        with self.assertRaisesRegex(
            connector.AffiliateRuntimeConnectorError,
            r"^ENVIRONMENT_UNAVAILABLE$",
        ):
            connector.fetch_item_response(
                content_id=CONTENT_ID,
                env_path=missing,
                fetcher=lambda *_args, **_kwargs: self.fail(
                    "request must not run"
                ),
            )

    def test_request_failure_does_not_echo_secrets(self):
        def failure(*_args, **_kwargs):
            raise RuntimeError(
                f"secret {API_ID} {AFFILIATE_ID} {CONTENT_ID}"
            )

        with self.assertRaises(
            connector.AffiliateRuntimeConnectorError
        ) as captured:
            connector.fetch_item_response(
                content_id=CONTENT_ID,
                env_path=self.env,
                fetcher=failure,
            )

        message = str(captured.exception)
        self.assertEqual(message, "CONNECTOR_INTERNAL_ERROR")
        self.assertNotIn(API_ID, message)
        self.assertNotIn(AFFILIATE_ID, message)
        self.assertNotIn(CONTENT_ID, message)


if __name__ == "__main__":
    unittest.main()
