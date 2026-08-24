from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from temporal_probe_state import (  # noqa: E402
    create_temporal_probe_state,
    deserialize_temporal_probe_state,
)
from temporal_probe_state_store import (  # noqa: E402
    DEFAULT_STATE_DIRECTORY,
    latest_previous_state,
    plan_state_write,
    safe_child_path,
    safe_state_filename,
    write_temporal_probe_state,
)


CAPTURED = datetime(2026, 8, 25, 5, 0, tzinfo=timezone.utc)
AS_OF = CAPTURED + timedelta(days=10)


def state(*, captured_at: datetime = CAPTURED, source_sort: str = "rank", offset: int = 1, hits: int = 100, content_id: str = "cid-001"):
    return create_temporal_probe_state(
        captured_at=captured_at,
        site="FANZA",
        service="digital",
        floor="videoa",
        source_sort=source_sort,
        offset=offset,
        hits=hits,
        content_ids=[content_id],
    )


class TemporalProbeStateStoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        DEFAULT_STATE_DIRECTORY.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls) -> None:
        try:
            DEFAULT_STATE_DIRECTORY.rmdir()
            DEFAULT_STATE_DIRECTORY.parent.rmdir()
        except OSError:
            pass

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(
            prefix="unit-", dir=DEFAULT_STATE_DIRECTORY
        )
        self.directory = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_a_valid_state_is_saved(self) -> None:
        result = write_temporal_probe_state(state(), output_directory=self.directory)
        self.assertTrue(result.success)
        self.assertTrue((self.directory / result.filename).is_file())

    def test_b_read_back_state_is_valid(self) -> None:
        value = state()
        result = write_temporal_probe_state(value, output_directory=self.directory)
        content = (self.directory / result.filename).read_text(encoding="utf-8")
        self.assertEqual(deserialize_temporal_probe_state(content), value)
        self.assertTrue(result.read_back_valid)

    def test_c_written_bytes_hash_matches(self) -> None:
        result = write_temporal_probe_state(state(), output_directory=self.directory)
        content = (self.directory / result.filename).read_bytes()
        self.assertEqual(hashlib.sha256(content).hexdigest(), result.sha256)

    def test_d_identical_save_is_idempotent(self) -> None:
        first = write_temporal_probe_state(state(), output_directory=self.directory)
        second = write_temporal_probe_state(state(), output_directory=self.directory)
        self.assertTrue(first.success and second.success)
        self.assertTrue(second.idempotent)

    def test_e_same_filename_different_content_conflicts(self) -> None:
        first = state(content_id="cid-001")
        second = state(content_id="cid-002")
        self.assertTrue(write_temporal_probe_state(first, output_directory=self.directory).success)
        result = write_temporal_probe_state(second, output_directory=self.directory)
        self.assertFalse(result.success)
        self.assertTrue(result.conflict)

    def test_f_invalid_state_is_rejected_before_write(self) -> None:
        invalid = replace(state(), returned_count=2)
        result = write_temporal_probe_state(invalid, output_directory=self.directory)
        self.assertFalse(result.success)
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_g_unexpected_field_document_is_not_a_state(self) -> None:
        document = state().to_dict()
        document["title"] = "forbidden"
        self.assertIsNone(deserialize_temporal_probe_state(document))
        result = write_temporal_probe_state(document, output_directory=self.directory)
        self.assertFalse(result.success)

    def test_h_symlink_output_directory_is_rejected(self) -> None:
        link = self.directory / "link"
        with mock.patch("temporal_probe_state_store._is_symlink", side_effect=lambda path: path == link):
            result = write_temporal_probe_state(state(), output_directory=link)
        self.assertFalse(result.success)

    def test_i_symlink_target_file_is_rejected(self) -> None:
        value = state()
        target = self.directory / safe_state_filename(value)
        with mock.patch("temporal_probe_state_store._is_symlink", side_effect=lambda path: path == target):
            result = write_temporal_probe_state(value, output_directory=self.directory)
        self.assertFalse(result.success)
        self.assertTrue(result.conflict)

    def test_j_dangerous_repository_paths_are_rejected(self) -> None:
        for path in (ROOT, ROOT / "scripts", ROOT / "db", ROOT / "dist", ROOT / ".git"):
            with self.subTest(path=path):
                self.assertFalse(plan_state_write(state(), output_directory=path).success)

    def test_k_repository_external_output_is_rejected(self) -> None:
        external = Path(tempfile.gettempdir()).resolve() / "data-lab-probe-state"
        self.assertFalse(plan_state_write(state(), output_directory=external).success)

    def test_l_path_traversal_filename_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            safe_child_path(self.directory, "../state.json")

    def test_m_latest_previous_uses_same_population(self) -> None:
        older = state(captured_at=CAPTURED)
        latest = state(captured_at=CAPTURED + timedelta(days=1))
        current = state(captured_at=CAPTURED + timedelta(days=2))
        write_temporal_probe_state(older, output_directory=self.directory)
        write_temporal_probe_state(latest, output_directory=self.directory)
        result = latest_previous_state(current, output_directory=self.directory, as_of=AS_OF)
        self.assertTrue(result.success)
        self.assertEqual(result.state, latest)

    def test_n_sort_difference_is_not_mixed(self) -> None:
        write_temporal_probe_state(state(source_sort="review"), output_directory=self.directory)
        result = latest_previous_state(state(captured_at=CAPTURED + timedelta(days=1)), output_directory=self.directory, as_of=AS_OF)
        self.assertIsNone(result.state)

    def test_o_offset_and_hits_differences_are_not_mixed(self) -> None:
        write_temporal_probe_state(state(offset=101), output_directory=self.directory)
        write_temporal_probe_state(state(hits=50), output_directory=self.directory)
        result = latest_previous_state(state(captured_at=CAPTURED + timedelta(days=1)), output_directory=self.directory, as_of=AS_OF)
        self.assertIsNone(result.state)

    def test_p_malformed_json_does_not_pollute_discovery(self) -> None:
        valid = state()
        write_temporal_probe_state(valid, output_directory=self.directory)
        malformed = self.directory / "rank-offset000001-hits100-20260824T000000000000Z.json"
        malformed.write_text("not-json", encoding="utf-8")
        result = latest_previous_state(state(captured_at=CAPTURED + timedelta(days=1)), output_directory=self.directory, as_of=AS_OF)
        self.assertEqual(result.state, valid)
        self.assertEqual(result.valid_candidates, 1)

    def test_q_internal_exception_fails_closed(self) -> None:
        with mock.patch("temporal_probe_state_store.serialize_temporal_probe_state", side_effect=RuntimeError):
            result = write_temporal_probe_state(state(), output_directory=self.directory)
        self.assertFalse(result.success)
        self.assertEqual(result.reason_codes, ("INTERNAL_STORE_ERROR",))

    def test_r_dry_run_changes_nothing(self) -> None:
        absent = self.directory / "not-created"
        before = set(self.directory.iterdir())
        result = plan_state_write(state(), output_directory=absent)
        self.assertTrue(result.success)
        self.assertFalse(absent.exists())
        self.assertEqual(set(self.directory.iterdir()), before)


if __name__ == "__main__":
    unittest.main()
