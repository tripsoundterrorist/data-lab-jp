from pathlib import Path
import hashlib
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_expansion_d1_overlap_audit as subject  # noqa: E402


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def candidate(path: Path):
    lines = ["BEGIN TRANSACTION;"]
    for index in range(300):
        public_id = f"itm_{index:024x}"
        lines.append(
            "INSERT INTO affiliate_item_lookup (public_id, content_id, updated_at) VALUES "
            f"('{public_id}', 'cid{index}', '1970-01-01T00:00:00Z');"
        )
    lines.append("COMMIT;")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def remote(path: Path, count: int):
    lines = ["BEGIN TRANSACTION;"]
    for index in range(count):
        public_id = f"itm_{index:024x}"
        lines.append(
            'INSERT INTO "affiliate_item_lookup" '
            '("public_id","content_id","rights_status","lifecycle_status",'
            '"verification_status","affiliate_enabled","updated_at") VALUES'
            f"('{public_id}','cid{index}','PENDING_SEPARATE_POLICY',"
            "'PENDING_OFFICIAL_CONFIRMATION','PENDING',0,'1970-01-01T00:00:00Z');"
        )
    lines.append("COMMIT;")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class ExpansionD1OverlapAuditTests(unittest.TestCase):
    def test_aggregate_overlap_does_not_expose_ids_or_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate_path = root / "candidate.sql"
            remote_path = root / "remote.sql"
            candidate(candidate_path)
            remote(remote_path, 250)
            result = subject.assess(
                remote_path, candidate_path,
                expected_remote_sha256=digest(remote_path),
                expected_candidate_sha256=digest(candidate_path),
            )
        self.assertEqual(result.status, subject.AUDITED)
        self.assertEqual(result.exact_mapping_match_count, 250)
        self.assertEqual(result.candidate_missing_count, 50)
        self.assertEqual(result.mapping_conflict_count, 0)
        self.assertFalse(result.candidate_ids_exposed)
        self.assertFalse(result.production_write_performed)
        self.assertFalse(result.publication_allowed)

    def test_identity_mismatch_blocks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate_path = root / "candidate.sql"
            remote_path = root / "remote.sql"
            candidate(candidate_path)
            remote(remote_path, 300)
            result = subject.assess(
                remote_path, candidate_path,
                expected_remote_sha256="0" * 64,
                expected_candidate_sha256=digest(candidate_path),
            )
        self.assertEqual(result.status, subject.BLOCKED)


if __name__ == "__main__":
    unittest.main()
