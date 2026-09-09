from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import temporal_probe_series_dry_orchestrator as orchestrator  # noqa: E402
import temporal_probe_series_state as series  # noqa: E402


BASE = datetime(2026, 9, 9, tzinfo=timezone.utc)
AS_OF = BASE + timedelta(days=4)
SERIES_ID = "series-20260909T000000Z-a1b2c3d4"

def state(identity, captured_at, values=("cid-1",)):
    source_sort, offset, hits = identity
    return series.create_temporal_probe_series_state(
        series_id=SERIES_ID,
        captured_at=captured_at,
        site="FANZA",
        service="digital",
        floor="videoa",
        source_sort=source_sort,
        offset=offset,
        hits=hits,
        content_ids=values,
    )


def current_states(captured_at):
    return tuple(
        state(identity, captured_at)
        for identity in orchestrator.FIXED_POPULATIONS
    )


def empty_documents():
    return {identity: () for identity in orchestrator.FIXED_POPULATIONS}


def histories(value):
    return {identity: value for identity in orchestrator.FIXED_POPULATIONS}


class TemporalProbeSeriesDryOrchestratorTests(unittest.TestCase):
    def test_four_explicit_baselines_are_planned_in_fixed_order(self):
        result = orchestrator.run_fixed_series_dry_orchestrator(
            current_states=current_states(BASE),
            documents_by_population=empty_documents(),
            history_counts=histories(0),
            as_of=AS_OF,
        )
        self.assertEqual(result.status, orchestrator.DRY_RUN_COMPLETE)
        self.assertTrue(result.success)
        self.assertEqual((result.succeeded_count, result.skipped_count), (4, 0))
        self.assertEqual(
            tuple((item.source_sort, item.offset, item.hits) for item in result.populations),
            orchestrator.FIXED_POPULATIONS,
        )
        self.assertTrue(all(
            item.status == "EXPLICIT_SERIES_BASELINE_PLANNED"
            for item in result.populations
        ))
        self.assertFalse(result.api_request_authorized)
        self.assertFalse(result.state_write_authorized)
        self.assertFalse(result.baseline_activation_authorized)

    def test_four_same_series_comparisons_are_assessed(self):
        documents = {
            identity: (series.serialize_temporal_probe_series_state(
                state(identity, BASE)
            ),)
            for identity in orchestrator.FIXED_POPULATIONS
        }
        result = orchestrator.run_fixed_series_dry_orchestrator(
            current_states=current_states(BASE + timedelta(days=1)),
            documents_by_population=documents,
            history_counts=histories(1),
            as_of=AS_OF,
        )
        self.assertEqual(result.status, orchestrator.DRY_RUN_COMPLETE)
        self.assertTrue(all(item.comparison_available for item in result.populations))
        self.assertTrue(all(
            item.stability_classification == "OBSERVATION_ONLY"
            for item in result.populations
        ))

    def test_first_blocked_result_stops_remaining_populations(self):
        documents = empty_documents()
        first = orchestrator.FIXED_POPULATIONS[0]
        documents[first] = (series.serialize_temporal_probe_series_state(
            state(first, BASE)
        ),)
        result = orchestrator.run_fixed_series_dry_orchestrator(
            current_states=current_states(BASE + timedelta(days=3)),
            documents_by_population=documents,
            history_counts=histories(1),
            as_of=AS_OF,
        )
        self.assertEqual(result.status, orchestrator.DRY_RUN_BLOCKED)
        self.assertEqual((result.failed_count, result.skipped_count), (1, 3))
        self.assertEqual(
            tuple(item.status for item in result.populations[1:]),
            ("NOT_RUN", "NOT_RUN", "NOT_RUN"),
        )

    def test_wrong_order_fails_before_evaluation(self):
        values = list(current_states(BASE))
        values[0], values[1] = values[1], values[0]
        result = orchestrator.run_fixed_series_dry_orchestrator(
            current_states=tuple(values),
            documents_by_population=empty_documents(),
            history_counts=histories(0),
            as_of=AS_OF,
        )
        self.assertEqual(result.status, orchestrator.DRY_RUN_BLOCKED)
        self.assertEqual(result.evaluated_count, 0)

    def test_missing_mapping_key_fails_closed(self):
        documents = empty_documents()
        del documents[orchestrator.FIXED_POPULATIONS[-1]]
        result = orchestrator.run_fixed_series_dry_orchestrator(
            current_states=current_states(BASE),
            documents_by_population=documents,
            history_counts=histories(0),
            as_of=AS_OF,
        )
        self.assertEqual(result.status, orchestrator.DRY_RUN_BLOCKED)

    def test_safe_output_contains_no_series_or_item_identifiers(self):
        result = orchestrator.run_fixed_series_dry_orchestrator(
            current_states=current_states(BASE, ),
            documents_by_population=empty_documents(),
            history_counts=histories(0),
            as_of=AS_OF,
        )
        encoded = json.dumps(result.to_dict())
        self.assertNotIn(SERIES_ID, encoded)
        self.assertNotIn("cid-1", encoded)
        self.assertNotIn("anonymous_item_ids", encoded)

    def test_source_has_no_filesystem_or_external_io(self):
        source = Path(orchestrator.__file__).read_text(encoding="utf-8")
        for forbidden in (
            "open(", "write_temporal_probe_state", "urllib", "requests",
            "subprocess", "fetch(",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
