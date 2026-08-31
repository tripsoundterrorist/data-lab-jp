import ast
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import queue_storage_inspection_callable_binding as binding  # noqa: E402
import queue_storage_inspection_trusted_evidence_collector as collector  # noqa: E402
import unattended_job_queue as core  # noqa: E402


class QueueStorageInspectionTrustedEvidenceCollectorTests(unittest.TestCase):
    def test_read_only_configuration_is_attested_but_activation_blocked(self):
        actual = collector.collect(
            binding.get_binding(), core.get_queue_identity())
        self.assertEqual(actual.collector_version, "0.1")
        self.assertEqual(actual.status, "PREFLIGHT_EVIDENCE_COLLECTED")
        self.assertTrue(actual.evidence_attested)
        self.assertFalse(actual.activation_allowed)
        self.assertFalse(actual.invocation_allowed)
        self.assertIsNotNone(actual.evidence)
        self.assertTrue(actual.evidence.production_write_disabled)
        self.assertTrue(actual.evidence.queue_identity_valid)
        self.assertEqual(actual.reason_codes,
                         ("READ_ONLY_PREFLIGHT_ATTESTED_ACTIVATION_BLOCKED",))

    def test_collection_does_not_create_or_change_runtime_entries(self):
        runtime = ROOT / "runtime"
        before = tuple(sorted(str(path.relative_to(runtime))
                              for path in runtime.rglob("*")))
        collector.collect(binding.get_binding(), core.get_queue_identity())
        after = tuple(sorted(str(path.relative_to(runtime))
                             for path in runtime.rglob("*")))
        self.assertEqual(after, before)

    def test_evidence_is_fixed_and_contains_no_path_or_identity(self):
        actual = collector.collect(
            binding.get_binding(), core.get_queue_identity()).evidence
        self.assertEqual(actual.observed_codes,
                         ("PRODUCTION_WRITE_DISABLED", "QUEUE_IDENTITY_VALID"))
        self.assertEqual(actual.max_runtime_seconds, 5)
        rendered = repr(actual)
        self.assertNotIn(str(ROOT), rendered)
        self.assertNotIn(core.get_queue_identity().queue_id, rendered)

    def test_invalid_binding_or_identity_blocks_collection(self):
        invalid_binding = replace(binding.get_binding(), callable_name="other")
        invalid_identity = replace(core.get_queue_identity(), queue_id="other")
        for bound, identity in (
            (invalid_binding, core.get_queue_identity()),
            (binding.get_binding(), invalid_identity),
        ):
            with self.subTest(bound=bound, identity=identity):
                actual = collector.collect(bound, identity)
                self.assertEqual(actual.status,
                                 "PREFLIGHT_EVIDENCE_COLLECTION_BLOCKED")
                self.assertFalse(actual.evidence_attested)
                self.assertIsNone(actual.evidence)

    def test_writable_store_configuration_is_rejected(self):
        queue_store = Mock()
        queue_store._write_enabled = True
        checkpoint_store = Mock()
        checkpoint_store._write_enabled = False
        with patch.object(
            collector.persistence, "_production_stores",
            return_value=(queue_store, checkpoint_store),
        ):
            actual = collector.collect(
                binding.get_binding(), core.get_queue_identity())
        self.assertIn("PRODUCTION_WRITE_DISABLE_NOT_PROVEN",
                      actual.reason_codes)
        self.assertFalse(actual.evidence_attested)

    def test_store_construction_exception_fails_closed(self):
        with patch.object(
            collector.persistence, "_production_stores",
            side_effect=RuntimeError("fixture"),
        ):
            actual = collector.collect(
                binding.get_binding(), core.get_queue_identity())
        self.assertEqual(actual.reason_codes,
                         ("EVIDENCE_COLLECTION_INTERNAL_ERROR",))
        self.assertFalse(actual.activation_allowed)

    def test_inspection_callable_is_never_invoked(self):
        with patch.object(
            collector.callable_binding.persistence,
            "inspect_production_queue_storage", autospec=True,
        ) as target, patch.object(
            collector.callable_binding, "_BOUND_CALLABLE", target,
        ):
            actual = collector.collect(
                binding.get_binding(), core.get_queue_identity())
        target.assert_not_called()
        self.assertTrue(actual.evidence_attested)

    def test_evidence_schema_is_revalidated(self):
        with patch.object(
            collector.evidence_contract, "validate_candidate",
            wraps=collector.evidence_contract.validate_candidate,
        ) as validate:
            collector.collect(binding.get_binding(), core.get_queue_identity())
        validate.assert_called_once()

    def test_collection_result_is_frozen(self):
        actual = collector.collect(
            binding.get_binding(), core.get_queue_identity())
        with self.assertRaises(FrozenInstanceError):
            actual.activation_allowed = True

    def test_no_inspection_invocation_write_notification_or_scheduler(self):
        tree = ast.parse(Path(collector.__file__).read_text(encoding="utf-8"))
        calls = {
            node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
            for node in ast.walk(tree) if isinstance(node, ast.Call)
            and isinstance(node.func, (ast.Attribute, ast.Name))
        }
        self.assertFalse(calls & {
            "open", "Popen", "run", "system", "save_queue",
            "initialize_for_test", "save_checkpoint",
            "load_production_queue_read_only",
            "inspect_production_queue_storage", "process_notification",
            "sleep", "activate", "invoke"})


if __name__ == "__main__":
    unittest.main()
