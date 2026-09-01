#!/usr/bin/env python3
"""Deterministic entry point for DATA LAB test tiers."""

from __future__ import annotations

import argparse
import compileall
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"

FAST_TEST_FILES = (
    "test_development_gate_ci_observation.py",
    "test_development_gate_coordinator.py",
    "test_development_gate_evidence.py",
    "test_development_fresh_usage_protected_start_adapter.py",
    "test_development_next_gate_usage_permit.py",
    "test_development_remote_approval_replay_persistence.py",
    "test_development_remote_approval_replay_record.py",
    "test_development_remote_iphone_approval_observation.py",
    "test_development_usage_evidence_freshness.py",
    "test_development_usage_protected_start_adapter.py",
    "test_development_usage_protection_permit.py",
    "test_durable_execution_adoption_coordinator.py",
    "test_durable_job_completion_coordinator.py",
    "test_github_actions_ci_contract.py",
    "test_notification_noise_control.py",
    "test_notification_incident_identity.py",
    "test_notification_incident_suppression_coordinator.py",
    "test_notification_incident_suppression_runner.py",
    "test_notification_ledger_record_v02.py",
    "test_notification_ledger_mixed_read.py",
    "test_notification_ledger_v02_writer.py",
    "test_queue_input_job_payload_contract.py",
    "test_queue_storage_inspection_trusted_evidence_collector.py",
    "test_unattended_queue_persistence.py",
)

TIERS = ("fast", "regression", "full")


def _validate_fast_manifest() -> tuple[str, ...]:
    if len(FAST_TEST_FILES) != len(set(FAST_TEST_FILES)):
        raise RuntimeError("FAST_TEST_MANIFEST_DUPLICATE")

    modules: list[str] = []
    for filename in FAST_TEST_FILES:
        if not filename.startswith("test_") or not filename.endswith(".py"):
            raise RuntimeError("FAST_TEST_MANIFEST_INVALID_NAME")
        if not (TESTS / filename).is_file():
            raise RuntimeError(f"FAST_TEST_MANIFEST_FILE_MISSING:{filename}")
        modules.append(filename.removesuffix(".py"))
    return tuple(modules)


def build_suite(tier: str) -> unittest.TestSuite:
    loader = unittest.TestLoader()
    if tier == "fast":
        modules = _validate_fast_manifest()
        return loader.loadTestsFromNames(modules)
    if tier in {"regression", "full"}:
        return loader.discover(str(TESTS), pattern="test_*.py")
    raise ValueError("UNKNOWN_TEST_TIER")


def run(tier: str, *, verbosity: int = 1) -> int:
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(TESTS))
    sys.path.insert(0, str(ROOT / "scripts"))

    if tier == "full" and not compileall.compile_dir(
        str(ROOT / "scripts"), quiet=1
    ):
        return 1
    if tier == "full" and not compileall.compile_dir(str(TESTS), quiet=1):
        return 1

    result = unittest.TextTestRunner(verbosity=verbosity).run(build_suite(tier))
    return 0 if result.wasSuccessful() else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tier", choices=TIERS)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    return run(args.tier, verbosity=2 if args.verbose else 1)


if __name__ == "__main__":
    raise SystemExit(main())
