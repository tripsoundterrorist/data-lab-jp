from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import temporal_probe_series_integration_adapter as adapter  # noqa: E402
import temporal_probe_series_state as series  # noqa: E402
from temporal_runbook_policy import FIXED_POPULATIONS  # noqa: E402


BASE = datetime(2026, 9, 9, tzinfo=timezone.utc)
AS_OF = BASE + timedelta(days=4)
SERIES_ID = "series-20260909T000000Z-a1b2c3d4"


def payloads():
    return [
        {
            "source_sort": source_sort,
            "offset": offset,
            "hits": hits,
            "result_count": 1,
            "items": [{"content_id": f"secret-{source_sort}-{offset}"}],
        }
        for source_sort, offset, hits in FIXED_POPULATIONS
    ]


def empty_documents():
    return {identity: () for identity in FIXED_POPULATIONS}


def histories(value):
    return {identity: value for identity in FIXED_POPULATIONS}


def previous_documents():
    values = {}
    for identity in FIXED_POPULATIONS:
        state = series.create_temporal_probe_series_state(
            series_id=SERIES_ID,
            captured_at=BASE,
            site="FANZA",
            service="digital",
            floor="videoa",
            source_sort=identity[0],
            offset=identity[1],
            hits=identity[2],
            content_ids=(f"secret-{identity[0]}-{identity[1]}",),
        )
        values[identity] = (series.serialize_temporal_probe_series_state(state),)
    return values


def run(values, *, captured_at=BASE, documents=None, history=0):
    return adapter.run_series_integration_dry_run(
        series_id=SERIES_ID,
        captured_at=captured_at,
        as_of=AS_OF,
        payloads=values,
        documents_by_population=(
            empty_documents() if documents is None else documents
        ),
        history_counts=histories(history),
    )


class TemporalProbeSeriesIntegrationAdapterTests(unittest.TestCase):
    def test_validates_four_payloads_and_plans_explicit_baselines(self):
        result = run(payloads())
        self.assertTrue(result.success)
        self.assertEqual(result.status, adapter.INTEGRATION_READY)
        self.assertEqual(result.validated_population_count, 4)
        self.assertTrue(all(
            item.status == "EXPLICIT_SERIES_BASELINE_PLANNED"
            for item in result.dry_run.populations
        ))
        self.assertFalse(result.active_pipeline_connected)
        self.assertFalse(result.api_request_authorized)
        self.assertFalse(result.state_write_authorized)
        self.assertFalse(result.baseline_activation_authorized)

    def test_same_series_comparisons_remain_observation_only(self):
        result = run(
            payloads(),
            captured_at=BASE + timedelta(days=1),
            documents=previous_documents(),
            history=1,
        )
        self.assertTrue(result.success)
        self.assertTrue(all(item.comparison_available for item in result.dry_run.populations))
        self.assertTrue(all(
            item.stability_classification == "OBSERVATION_ONLY"
            for item in result.dry_run.populations
        ))

    def test_wrong_order_fails_before_any_evaluation(self):
        values = payloads()
        values[0], values[1] = values[1], values[0]
        result = run(values)
        self.assertFalse(result.success)
        self.assertEqual(result.validated_population_count, 0)
        self.assertIsNone(result.dry_run)

    def test_count_mismatch_fails_closed(self):
        values = payloads()
        values[0]["result_count"] = 2
        self.assertEqual(run(values).reason_codes, ("MALFORMED_POPULATION_PAYLOAD",))

    def test_duplicate_content_id_fails_closed(self):
        values = payloads()
        values[0]["result_count"] = 2
        values[0]["items"] *= 2
        self.assertEqual(run(values).reason_codes, ("DUPLICATE_CONTENT_ID",))

    def test_extra_item_field_fails_closed(self):
        values = payloads()
        values[0]["items"][0]["title"] = "must not pass"
        self.assertEqual(run(values).reason_codes, ("MALFORMED_POPULATION_PAYLOAD",))

    def test_safe_output_contains_no_series_or_content_identifiers(self):
        encoded = json.dumps(run(payloads()).to_dict())
        self.assertNotIn(SERIES_ID, encoded)
        self.assertNotIn("secret-rank-1", encoded)

    def test_source_has_no_external_or_filesystem_io(self):
        source = Path(adapter.__file__).read_text(encoding="utf-8")
        for forbidden in (
            "open(", "write_temporal_probe_state", "urllib", "requests",
            "subprocess", "fetch(",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
