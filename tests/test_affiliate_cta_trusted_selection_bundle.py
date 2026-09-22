from dataclasses import replace
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import affiliate_cta_canonical_selection_preflight as preflight
import affiliate_cta_trusted_selection_bundle as subject


def receipt(**changes):
    value = preflight.CanonicalSelectionReceipt(
        preflight.VERSION, subject.CANONICALIZATION_VERSION, preflight.READY,
        subject.SOURCE_DATABASE_SHA256, subject.LIVE_ARTIFACT_SHA256,
        subject.SELECTION_DIGEST, subject.EXACT_SELECTION_COUNT,
        subject.EXACT_SELECTION_COUNT, subject.EXACT_SELECTION_COUNT,
    )
    return replace(value, **changes)


class TrustedSelectionBundleTests(unittest.TestCase):
    def test_exact_safe_canonical_receipt_becomes_fixed_bundle(self):
        result = subject.from_canonical_preflight(receipt())
        self.assertIsNotNone(result)
        self.assertTrue(subject.valid_bundle(result))
        self.assertNotIn("itm_", repr(result))

    def test_any_hash_count_or_capability_tamper_blocks_bundle_creation(self):
        for value in (
            receipt(selection_digest="0" * 64),
            receipt(source_database_sha256="0" * 64),
            receipt(live_artifact_sha256="0" * 64),
            receipt(selected_count=9),
            receipt(submitted_count=9),
            receipt(api_request_attempt_count=9),
            receipt(cta_activation_allowed=True),
        ):
            with self.subTest(value=value):
                self.assertIsNone(subject.from_canonical_preflight(value))

    def test_non_receipt_and_mutated_bundle_are_rejected(self):
        self.assertIsNone(subject.from_canonical_preflight({}))
        value = subject.from_canonical_preflight(receipt())
        assert value is not None
        self.assertFalse(subject.valid_bundle(replace(value, selected_count=9)))


if __name__ == "__main__":
    unittest.main()
