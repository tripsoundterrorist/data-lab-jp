from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_offline_artifact_integration as integration  # noqa: E402
import revenue_mvp_source_artifact_revalidation as revalidation  # noqa: E402
from product_verification import Observation, VerificationObservation  # noqa: E402
from revenue_mvp_lifecycle_receipt import LifecycleReceipt  # noqa: E402
from revenue_mvp_official_lifecycle_policy import InventorySignal  # noqa: E402
from tests.test_revenue_mvp_offline_artifact_integration import (  # noqa: E402
    PUBLIC_ID,
    evidence,
    fixture,
    gate,
)


STAMP = datetime(2026, 9, 20, 7, 0, 49, tzinfo=timezone.utc)
EXPECTED_SHA256 = "a" * 64


def handoff(ready=True):
    return SimpleNamespace(
        status="HANDOFF_READY" if ready else "BLOCKED",
        identity_verified=ready,
        items_count=1,
        reason_codes=(
            ("DB_HANDOFF_VERIFIED",)
            if ready
            else ("DATABASE_IDENTITY_MISMATCH",)
        ),
    )


def receipts(_database, _as_of):
    return (SimpleNamespace(public_id=PUBLIC_ID),)


def build(_database, _as_of, _generated_at, _receipts):
    return fixture(), {}


def valid_evidence(_files, _receipts):
    return {PUBLIC_ID: evidence()}, ()


class SourceArtifactRevalidationTests(unittest.TestCase):
    def run(self, result=None, **kwargs):
        if result is not None:
            return super().run(result)
        return revalidation.run_revalidation(
            Path("source.db"),
            EXPECTED_SHA256,
            as_of=STAMP,
            generated_at=STAMP,
            receipt_loader=receipts,
            artifact_builder=build,
            evidence_builder=valid_evidence,
            **kwargs,
        )

    def test_valid_in_memory_pipeline_is_review_evidence_only(self):
        with mock.patch.object(
            revalidation.db_handoff,
            "preflight",
            side_effect=(handoff(), handoff()),
        ) as preflight:
            result = self.run()
        self.assertEqual(preflight.call_count, 2)
        self.assertEqual(result.status, revalidation.READY)
        self.assertTrue(result.database_identity_verified)
        self.assertEqual(result.input_artifact_item_count, 1)
        self.assertEqual(result.filtered_artifact_item_count, 1)
        self.assertEqual(result.artifact_validation, "PASS")
        self.assertFalse(result.output_written)
        self.assertFalse(result.publication_allowed)
        self.assertFalse(result.production_write_performed)
        self.assertFalse(result.affiliate_eligibility_allowed)
        self.assertFalse(result.gate_mutation_allowed)
        self.assertEqual(result.api_calls, 0)
        self.assertFalse(result.network_io_performed)

    def test_default_build_retains_safe_base_before_lifecycle_filtering(self):
        class Builder:
            def __init__(self):
                self.master_items = {
                    value: {"public_id": f"itm_{value:024x}"}
                    for value in range(1000)
                }
                self.filter_master_items_by_lifecycle_receipts = (
                    lambda master, _confidence, _receipts, **_kwargs:
                    ({}, len(master))
                )
                self.original_prefilter = (
                    self.filter_master_items_by_lifecycle_receipts
                )
                self.reached = 0

            def build_documents(
                self,
                _database,
                _as_of,
                _generated_at,
                *,
                lifecycle_receipts,
            ):
                selected, excluded = (
                    self.filter_master_items_by_lifecycle_receipts(
                        self.master_items,
                        {},
                        lifecycle_receipts,
                        evaluated_at=STAMP,
                    )
                )
                self.reached = len(selected)
                return {"marker.json": b"{}"}, {"excluded": excluded}

        builder = Builder()
        with mock.patch.object(
            revalidation,
            "_load_script",
            return_value=builder,
        ):
            _files, summary = revalidation._default_build(
                Path("source.db"),
                STAMP,
                STAMP,
                (),
            )
        self.assertEqual(builder.reached, 1000)
        self.assertEqual(summary["excluded"], 0)
        self.assertIs(
            builder.filter_master_items_by_lifecycle_receipts,
            builder.original_prefilter,
        )

    def test_thousand_item_base_reaches_evidence_evaluation(self):
        base_files = {
            f"candidate-{value}.json": b"{}"
            for value in range(1000)
        }
        reached = []

        def inspect_evidence(files, _receipts):
            reached.append(len(files))
            return {}, (
                "LIFECYCLE_UNCONFIRMED",
                "REDUCED_SURFACE_SEMANTICS_UNCONFIRMED",
            )

        validations = (
            SimpleNamespace(
                artifact_validation="PASS",
                item_count=1000,
                reason_codes=(),
            ),
            SimpleNamespace(
                artifact_validation="PASS",
                item_count=0,
                reason_codes=(),
            ),
        )
        filtered = SimpleNamespace(
            status=integration.COMPLETE,
            files={"filtered.json": b"{}"},
            included_item_count=0,
            reason_codes=(),
        )
        with (
            mock.patch.object(
                revalidation.db_handoff,
                "preflight",
                return_value=handoff(),
            ),
            mock.patch.object(
                revalidation.validator,
                "validate_artifacts",
                side_effect=validations,
            ),
            mock.patch.object(
                revalidation.integration,
                "filter_offline_publication_artifacts",
                return_value=filtered,
            ),
        ):
            result = revalidation.run_revalidation(
                Path("source.db"),
                EXPECTED_SHA256,
                as_of=STAMP,
                generated_at=STAMP,
                receipt_loader=lambda *_args: tuple(range(1000)),
                artifact_builder=lambda *_args: (base_files, {}),
                evidence_builder=inspect_evidence,
            )
        self.assertEqual(reached, [1000])
        self.assertEqual(result.input_artifact_item_count, 1000)
        self.assertEqual(result.status, revalidation.FAIL_CLOSED)
        self.assertIn("LIFECYCLE_UNCONFIRMED", result.reason_codes)
        self.assertIn(
            "REDUCED_SURFACE_SEMANTICS_UNCONFIRMED",
            result.reason_codes,
        )

    def test_explicit_new_temp_output_is_revalidated(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "candidate"
            with mock.patch.object(
                revalidation.db_handoff,
                "preflight",
                side_effect=(handoff(), handoff()),
            ):
                result = self.run(output_directory=output)
            self.assertTrue(output.is_dir())
            self.assertEqual(
                {path.relative_to(output).as_posix() for path in output.rglob("*.json")},
                set(fixture()),
            )
        self.assertEqual(result.status, revalidation.READY)
        self.assertTrue(result.output_written)

    def test_final_identity_failure_never_exposes_staged_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "candidate"
            with mock.patch.object(
                revalidation.db_handoff,
                "preflight",
                side_effect=(handoff(), handoff(False)),
            ) as preflight:
                result = self.run(output_directory=output)
            self.assertEqual(preflight.call_count, 2)
            self.assertFalse(output.exists())
            self.assertEqual(tuple(root.glob("candidate.stage-*")), ())
        self.assertEqual(result.status, revalidation.FAIL_CLOSED)
        self.assertFalse(result.database_identity_verified)
        self.assertFalse(result.output_written)
        self.assertIn("DATABASE_CHANGED_DURING_REVALIDATION", result.reason_codes)

    def test_database_identity_mismatch_stops_before_receipt_read(self):
        loader = mock.Mock()
        with mock.patch.object(
            revalidation.db_handoff,
            "preflight",
            return_value=handoff(False),
        ):
            result = revalidation.run_revalidation(
                Path("source.db"),
                EXPECTED_SHA256,
                as_of=STAMP,
                generated_at=STAMP,
                receipt_loader=loader,
            )
        loader.assert_not_called()
        self.assertEqual(result.status, revalidation.FAIL_CLOSED)
        self.assertIn("DATABASE_IDENTITY_MISMATCH", result.reason_codes)

    def test_zero_candidate_artifact_fails_closed(self):
        empty = integration.filter_offline_publication_artifacts(
            fixture(),
            {PUBLIC_ID: evidence(False)},
        ).files

        def empty_build(*_args):
            return empty, {}

        with mock.patch.object(
            revalidation.db_handoff,
            "preflight",
            return_value=handoff(),
        ):
            result = revalidation.run_revalidation(
                Path("source.db"),
                EXPECTED_SHA256,
                as_of=STAMP,
                generated_at=STAMP,
                receipt_loader=lambda *_args: (),
                artifact_builder=empty_build,
                evidence_builder=lambda *_args: ({}, ()),
            )
        self.assertEqual(result.status, revalidation.FAIL_CLOSED)
        self.assertEqual(result.filtered_artifact_item_count, 0)
        self.assertIn(
            "ZERO_OR_INCONSISTENT_CANDIDATE_ITEMS",
            result.reason_codes,
        )
        self.assertIn("LIFECYCLE_CANDIDATE_REQUIRED", result.reason_codes)
        self.assertIn(
            "REDUCED_SURFACE_SEMANTICS_NOT_EVALUATED",
            result.reason_codes,
        )

    def test_unknown_lifecycle_or_semantics_fails_closed(self):
        def uncertain(files, loaded_receipts):
            values, _ = valid_evidence(files, loaded_receipts)
            return values, ("REDUCED_SURFACE_SEMANTICS_UNCONFIRMED",)

        with mock.patch.object(
            revalidation.db_handoff,
            "preflight",
            side_effect=(handoff(), handoff()),
        ):
            result = revalidation.run_revalidation(
                Path("source.db"),
                EXPECTED_SHA256,
                as_of=STAMP,
                generated_at=STAMP,
                receipt_loader=receipts,
                artifact_builder=build,
                evidence_builder=uncertain,
            )
        self.assertEqual(result.status, revalidation.FAIL_CLOSED)
        self.assertIn(
            "REDUCED_SURFACE_SEMANTICS_UNCONFIRMED",
            result.reason_codes,
        )

    def test_default_evidence_reports_concrete_unknown_reasons(self):
        receipt = LifecycleReceipt(
            "0.1",
            PUBLIC_ID,
            VerificationObservation(
                Observation.UNKNOWN,
                STAMP,
                None,
                None,
                None,
                ("SAVED_AFFILIATE_EVIDENCE_UNAVAILABLE",),
            ),
            InventorySignal.UNKNOWN,
            False,
            STAMP,
            86400,
        )
        values, reasons = revalidation._default_item_evidence(
            fixture(),
            (receipt,),
        )
        self.assertEqual(set(values), {PUBLIC_ID})
        self.assertIn("OBSERVATION_NOT_ELIGIBLE", reasons)
        self.assertIn("LIFECYCLE_NOT_ELIGIBLE", reasons)
        self.assertIn("SOURCE_SORT_UNSUPPORTED", reasons)

    def test_saved_visible_affiliate_receipt_is_lifecycle_only_candidate(self):
        receipt = LifecycleReceipt(
            "0.1",
            PUBLIC_ID,
            VerificationObservation(
                Observation.API_ITEM_VISIBLE,
                STAMP,
                True,
                True,
                200,
                (
                    "AFFILIATE_URL_VALIDATED",
                    "COLLECTION_ITEM_IDENTITY_MATCH_OBSERVED",
                ),
            ),
            InventorySignal.UNKNOWN,
            True,
            STAMP,
            86400,
        )
        with mock.patch.object(
            revalidation.publication_gate,
            "evaluate_publication_gate",
            return_value=gate(),
        ):
            values, reasons = revalidation._default_item_evidence(
                fixture(),
                (receipt,),
            )
        value = values[PUBLIC_ID]
        self.assertEqual(
            value.lifecycle.status,
            revalidation.lifecycle_filter.INCLUDE_CANDIDATE,
        )
        self.assertFalse(value.lifecycle.affiliate_cta_candidate)
        self.assertFalse(value.lifecycle.api_order_label_allowed)
        self.assertEqual(
            value.reduced_surface.status,
            revalidation.reduced_surface.INVALID_INPUT,
        )
        self.assertIn("REDUCED_SURFACE_SEMANTICS_UNCONFIRMED", reasons)
        self.assertNotIn("LIFECYCLE_UNCONFIRMED", reasons)
        self.assertNotIn("OFFLINE_LIFECYCLE_FILTER_BLOCKED", reasons)

    def test_database_change_after_filtering_fails_closed(self):
        with mock.patch.object(
            revalidation.db_handoff,
            "preflight",
            side_effect=(handoff(), handoff(False)),
        ):
            result = self.run()
        self.assertEqual(result.status, revalidation.FAIL_CLOSED)
        self.assertFalse(result.database_identity_verified)
        self.assertIn("DATABASE_CHANGED_DURING_REVALIDATION", result.reason_codes)

    def test_early_failure_still_runs_final_identity_check(self):
        with mock.patch.object(
            revalidation.db_handoff,
            "preflight",
            side_effect=(handoff(), handoff(False)),
        ) as preflight:
            result = revalidation.run_revalidation(
                Path("source.db"),
                EXPECTED_SHA256,
                as_of=STAMP,
                generated_at=STAMP,
                receipt_loader=lambda *_args: [],
            )
        self.assertEqual(preflight.call_count, 2)
        self.assertEqual(result.status, revalidation.FAIL_CLOSED)
        self.assertFalse(result.database_identity_verified)
        self.assertIn("LIFECYCLE_RECEIPTS_INVALID", result.reason_codes)
        self.assertIn("DATABASE_CHANGED_DURING_REVALIDATION", result.reason_codes)

    def test_sqlite_wal_update_cannot_preserve_ready_identity(self):
        connections = []
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "source.db"
            connection = sqlite3.connect(database)
            connection.execute("CREATE TABLE state(value INTEGER NOT NULL)")
            connection.execute("INSERT INTO state VALUES (1)")
            connection.commit()
            connection.close()
            expected = hashlib.sha256(database.read_bytes()).hexdigest()

            def mutate_in_wal(_database, _as_of):
                writer = sqlite3.connect(database)
                self.assertEqual(
                    writer.execute("PRAGMA journal_mode=WAL").fetchone()[0],
                    "wal",
                )
                writer.execute("UPDATE state SET value = 2")
                writer.commit()
                connections.append(writer)
                self.assertTrue(Path(f"{database}-wal").is_file())
                return []

            with mock.patch.object(
                revalidation.db_handoff,
                "preflight",
                return_value=handoff(),
            ):
                result = revalidation.run_revalidation(
                    database,
                    expected,
                    as_of=STAMP,
                    generated_at=STAMP,
                    receipt_loader=mutate_in_wal,
                )
            observed = connections[0].execute(
                "SELECT value FROM state"
            ).fetchone()[0]
            for writer in connections:
                writer.close()
        self.assertEqual(observed, 2)
        self.assertEqual(result.status, revalidation.FAIL_CLOSED)
        self.assertFalse(result.database_identity_verified)
        self.assertIn("SQLITE_SIDECAR_PRESENT", result.reason_codes)
        self.assertIn("DATABASE_CHANGED_DURING_REVALIDATION", result.reason_codes)

    def test_invalid_hash_and_timestamps_fail_before_preflight(self):
        preflight = mock.Mock()
        with mock.patch.object(revalidation.db_handoff, "preflight", preflight):
            bad_hash = revalidation.run_revalidation(
                Path("source.db"),
                "unknown",
                as_of=STAMP,
                generated_at=STAMP,
            )
            bad_time = revalidation.run_revalidation(
                Path("source.db"),
                EXPECTED_SHA256,
                as_of=datetime(2026, 9, 20),
                generated_at=STAMP,
            )
        preflight.assert_not_called()
        self.assertEqual(bad_hash.status, revalidation.FAIL_CLOSED)
        self.assertEqual(bad_time.status, revalidation.FAIL_CLOSED)

    def test_existing_or_repo_output_path_fails_closed_without_path_leak(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = self.run(output_directory=Path(temporary))
            rendered = json.dumps(result.to_dict())
            self.assertNotIn(temporary, rendered)
        repo_result = self.run(output_directory=ROOT / "candidate")
        self.assertEqual(result.status, revalidation.FAIL_CLOSED)
        self.assertEqual(repo_result.status, revalidation.FAIL_CLOSED)

    def test_result_contains_no_identifier_url_secret_or_path(self):
        with mock.patch.object(
            revalidation.db_handoff,
            "preflight",
            side_effect=(handoff(), handoff()),
        ):
            rendered = json.dumps(self.run().to_dict()).casefold()
        for forbidden in (
            PUBLIC_ID,
            "content_id",
            "affiliate_url",
            "affiliate_id",
            "api_id",
            "credential",
            "source.db",
            "http://",
            "https://",
        ):
            self.assertNotIn(forbidden, rendered)

    def test_untrusted_reason_is_replaced_without_marker_leak(self):
        marker = (
            "https://invalid.example/?"
            + "affiliate"
            + "_id"
            + "=secret-C:\\private"
        )

        def malicious_reason(files, loaded_receipts):
            values, _ = valid_evidence(files, loaded_receipts)
            return values, (marker,)

        with mock.patch.object(
            revalidation.db_handoff,
            "preflight",
            side_effect=(handoff(), handoff()),
        ):
            result = revalidation.run_revalidation(
                Path("source.db"),
                EXPECTED_SHA256,
                as_of=STAMP,
                generated_at=STAMP,
                receipt_loader=receipts,
                artifact_builder=build,
                evidence_builder=malicious_reason,
            )
        rendered = json.dumps(result.to_dict())
        self.assertEqual(result.status, revalidation.FAIL_CLOSED)
        self.assertIn("UNTRUSTED_REASON_CODE_REJECTED", result.reason_codes)
        self.assertNotIn("invalid.example", rendered)
        self.assertNotIn("affiliate_id", rendered)
        self.assertNotIn("secret", rendered.casefold())
        self.assertNotIn("private", rendered.casefold())


if __name__ == "__main__":
    unittest.main()
