from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import temporal_probe_series_connection_harness as harness  # noqa: E402
import temporal_probe_series_integration_adapter as adapter  # noqa: E402
import temporal_probe_validated_bundle_dry_connection as connection  # noqa: E402
from temporal_runbook_policy import FIXED_POPULATIONS  # noqa: E402


BASE = datetime(2026, 9, 9, tzinfo=timezone.utc)
AS_OF = BASE + timedelta(days=4)
SERIES_ID = "series-20260909T000000Z-a1b2c3d4"


def payloads():
    return [
        {
            "source_sort": source_sort, "offset": offset, "hits": hits,
            "result_count": 1,
            "items": [{"content_id": f"private-{source_sort}-{offset}"}],
        }
        for source_sort, offset, hits in FIXED_POPULATIONS
    ]


def bundle():
    return adapter.build_validated_series_state_bundle(
        series_id=SERIES_ID, captured_at=BASE, as_of=AS_OF,
        payloads=payloads(),
    )


def documents():
    return {identity: () for identity in FIXED_POPULATIONS}


def histories(value=0):
    return {identity: value for identity in FIXED_POPULATIONS}


_MISSING = object()


def connect(value=_MISSING, *, docs=None, counts=None):
    return connection.connect_validated_bundle_to_dry_harness(
        bundle=bundle() if value is _MISSING else value,
        documents_by_population=documents() if docs is None else docs,
        history_counts=histories() if counts is None else counts,
        as_of=AS_OF,
    )


class TemporalProbeValidatedBundleDryConnectionTests(unittest.TestCase):
    def test_public_bundle_connects_once_to_existing_harness(self):
        value = bundle()
        with mock.patch.object(
            connection.harness, "run_dry_connection_harness",
            wraps=harness.run_dry_connection_harness,
        ) as run:
            result = connect(value)
        self.assertEqual(result.version, "0.1-candidate")
        self.assertEqual(result.status, connection.CONNECTION_COMPLETE)
        self.assertTrue(result.success)
        self.assertEqual(result.validated_population_count, 4)
        run.assert_called_once_with(
            current_states=value.states,
            documents_by_population=mock.ANY,
            history_counts=mock.ANY,
            as_of=AS_OF,
        )

    def test_connector_does_not_rebuild_or_privately_validate_bundle(self):
        value = bundle()
        with mock.patch.object(
            connection.adapter, "build_validated_series_state_bundle",
            side_effect=AssertionError,
        ), mock.patch.object(
            connection.adapter, "_content_ids", side_effect=AssertionError,
        ):
            self.assertTrue(connect(value).success)

    def test_modified_or_failed_envelope_blocks_before_harness(self):
        valid = bundle()
        cases = (
            None, {},
            replace(valid, version="unknown"),
            replace(valid, success=False),
            replace(valid, validated_population_count=3),
            replace(valid, states=valid.states[:-1]),
            replace(valid, active_pipeline_connected=True),
            replace(valid, api_request_authorized=True),
            replace(valid, state_write_authorized=True),
            replace(valid, reason_codes=("UNKNOWN",)),
        )
        for value in cases:
            with self.subTest(value=value), mock.patch.object(
                connection.harness, "run_dry_connection_harness",
            ) as run:
                result = connect(value)
            self.assertEqual(result.reason_codes,
                             ("VALIDATED_STATE_BUNDLE_INVALID",))
            self.assertIsNone(result.dry_harness)
            run.assert_not_called()

    def test_modified_state_is_rejected_by_harness_not_duplicate_validation(self):
        valid = bundle()
        swapped = replace(
            valid, states=(valid.states[1], valid.states[0], *valid.states[2:]))
        with mock.patch.object(
            connection.harness, "run_dry_connection_harness",
            wraps=harness.run_dry_connection_harness,
        ) as run:
            result = connect(swapped)
        self.assertEqual(result.reason_codes, ("DRY_HARNESS_BLOCKED",))
        run.assert_called_once()

    def test_downstream_input_failure_is_bounded(self):
        docs = documents()
        del docs[FIXED_POPULATIONS[-1]]
        result = connect(bundle(), docs=docs)
        self.assertEqual(result.reason_codes, ("DRY_HARNESS_BLOCKED",))
        self.assertIsNone(result.dry_harness)

    def test_unknown_or_permissive_harness_result_blocks(self):
        invalid = harness.SeriesConnectionHarnessResult(
            harness.HARNESS_VERSION, harness.HARNESS_BLOCKED, False,
            0, 0, 0, 4, True, True, False, False, False, False, (),
            ("FIXTURE",),
        )
        for value in (object(), invalid):
            with self.subTest(value=value), mock.patch.object(
                connection.harness, "run_dry_connection_harness",
                return_value=value,
            ):
                result = connect(bundle())
            self.assertEqual(result.reason_codes,
                             ("DRY_HARNESS_RESULT_INVALID",))

    def test_safe_output_and_non_authorization_flags(self):
        result = connect(bundle())
        encoded = json.dumps(result.to_dict()) + repr(result)
        self.assertNotIn(SERIES_ID, encoded)
        self.assertNotIn("private-rank-1", encoded)
        self.assertFalse(result.active_pipeline_connected)
        self.assertFalse(result.filesystem_access_performed)
        self.assertFalse(result.api_request_authorized)
        self.assertFalse(result.state_write_authorized)
        self.assertFalse(result.baseline_activation_authorized)

    def test_exception_fails_closed_without_details(self):
        with mock.patch.object(
            connection.harness, "run_dry_connection_harness",
            side_effect=RuntimeError("fixture-secret"),
        ):
            result = connect(bundle())
        self.assertEqual(result.reason_codes,
                         ("VALIDATED_BUNDLE_DRY_CONNECTION_ERROR",))
        self.assertNotIn("fixture-secret", repr(result))

    def test_source_has_no_active_or_write_surfaces(self):
        source = Path(connection.__file__).read_text(encoding="utf-8")
        for forbidden in (
            "build_validated_series_state_bundle(", "_content_ids(",
            "validate_temporal_probe_series_state(", "run_temporal_probe(",
            "open(", "read_text(", "read_bytes(", "write_text(",
            "write_bytes(", "mkdir(", "unlink(", "sqlite", "d1",
            "urllib", "requests", "subprocess", "fetch(", "deploy",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
