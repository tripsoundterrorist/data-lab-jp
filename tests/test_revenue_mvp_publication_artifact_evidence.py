from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_publication_artifact_evidence as evidence  # noqa: E402


class PublicationArtifactEvidenceTests(unittest.TestCase):
    def test_matching_receipt_and_database_are_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "data-lab.db"
            database.write_bytes(b"fixture database")
            receipt = Path(directory) / "receipt.json"
            value = json.loads(evidence.RECEIPT.read_text(encoding="utf-8"))
            import hashlib
            value["source_db_sha256"] = hashlib.sha256(database.read_bytes()).hexdigest()
            receipt.write_text(json.dumps(value), encoding="utf-8")
            with (
                mock.patch.object(evidence, "DB", database),
                mock.patch.object(evidence, "RECEIPT", receipt),
            ):
                result = evidence.assess_evidence()
        self.assertEqual(result.status, evidence.EVIDENCE_READY)
        self.assertTrue(result.source_db_matches)
        self.assertTrue(result.artifact_validation_passed)
        self.assertEqual(result.item_count, 865)
        self.assertFalse(result.publication_allowed)
        self.assertFalse(result.production_write_performed)
        self.assertFalse(result.gate_unlock_allowed)

    def test_changed_database_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            changed = Path(directory) / "changed.db"
            changed.write_bytes(b"changed")
            with mock.patch.object(evidence, "DB", changed):
                result = evidence.assess_evidence()
        self.assertEqual(result.status, evidence.BLOCKED)
        self.assertFalse(result.source_db_matches)

    def test_permissive_or_malformed_receipt_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            receipt = Path(directory) / "receipt.json"
            receipt.write_text(json.dumps({"gate_unlock_allowed": True}), encoding="utf-8")
            with mock.patch.object(evidence, "RECEIPT", receipt):
                result = evidence.assess_evidence()
        self.assertEqual(result.status, evidence.BLOCKED)
        self.assertFalse(result.gate_unlock_allowed)


if __name__ == "__main__":
    unittest.main()
