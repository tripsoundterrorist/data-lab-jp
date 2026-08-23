from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from typing import Iterator, Mapping, Any
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from product_verification import Observation, evaluate_product_verification


NOW = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)


def fixture(**updates: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "expected_content_id": "cid-001",
        "observed_at": NOW - timedelta(minutes=1),
        "call_status": "success",
        "error_class": None,
        "source_status_code": 200,
        "result_count": 1,
        "items": [
            {"content_id": "cid-001", "affiliate_link_present": None}
        ],
    }
    value.update(updates)
    return value


def evaluate(value: Mapping[str, Any]):
    return evaluate_product_verification(value, as_of=NOW)


class ProductVerificationContractTests(unittest.TestCase):
    def test_a_exact_single_item_is_visible(self) -> None:
        result = evaluate(fixture())
        self.assertEqual(result.observation, Observation.API_ITEM_VISIBLE)
        self.assertIs(result.expected_content_id_match, True)

    def test_b_empty_result_is_only_not_returned(self) -> None:
        result = evaluate(fixture(result_count=0, items=[]))
        self.assertEqual(result.observation, Observation.API_ITEM_NOT_RETURNED)
        self.assertEqual(result.reason_codes, ("ITEM_NOT_RETURNED_NO_BUSINESS_MEANING",))

    def test_c_zero_count_with_item_is_malformed(self) -> None:
        result = evaluate(fixture(result_count=0))
        self.assertEqual(result.observation, Observation.MALFORMED_RESPONSE)

    def test_d_one_count_with_no_items_is_malformed(self) -> None:
        result = evaluate(fixture(items=[]))
        self.assertEqual(result.observation, Observation.MALFORMED_RESPONSE)

    def test_e_content_id_mismatch(self) -> None:
        result = evaluate(fixture(items=[{"content_id": "cid-002", "affiliate_link_present": True}]))
        self.assertEqual(result.observation, Observation.CID_MISMATCH)
        self.assertIs(result.expected_content_id_match, False)
        self.assertIsNone(result.affiliate_link_observed)

    def test_f_multiple_items(self) -> None:
        items = [
            {"content_id": "cid-001", "affiliate_link_present": True},
            {"content_id": "cid-002", "affiliate_link_present": False},
        ]
        result = evaluate(fixture(result_count=2, items=items))
        self.assertEqual(result.observation, Observation.MULTIPLE_ITEMS_RETURNED)

    def test_g_rate_limit(self) -> None:
        result = evaluate(fixture(call_status="failure", error_class="rate_limited", result_count=None, items=[], source_status_code=429))
        self.assertEqual(result.observation, Observation.API_RATE_LIMITED)
        self.assertEqual(result.reason_codes, ("SOURCE_RATE_LIMITED",))

    def test_h_transient_error_is_only_api_error(self) -> None:
        result = evaluate(fixture(call_status="failure", error_class="transient_error", result_count=None, items=[], source_status_code=503))
        self.assertEqual(result.observation, Observation.API_ERROR)
        self.assertEqual(result.reason_codes, ("SOURCE_TRANSIENT_ERROR",))

    def test_i_unknown_error_fails_closed(self) -> None:
        result = evaluate(fixture(call_status="failure", error_class="unknown_error", result_count=None, items=[], source_status_code="UNKNOWN"))
        self.assertEqual(result.observation, Observation.UNKNOWN)

    def test_j_affiliate_presence_is_boolean_observation(self) -> None:
        result = evaluate(fixture(items=[{"content_id": "cid-001", "affiliate_link_present": True}]))
        self.assertIs(result.affiliate_link_observed, True)

    def test_k_affiliate_absence_or_unknown_stays_observational(self) -> None:
        absent = evaluate(fixture(items=[{"content_id": "cid-001", "affiliate_link_present": False}]))
        unknown = evaluate(fixture())
        self.assertIs(absent.affiliate_link_observed, False)
        self.assertIsNone(unknown.affiliate_link_observed)

    def test_l_malformed_affiliate_field_fails_closed(self) -> None:
        result = evaluate(fixture(items=[{"content_id": "cid-001", "affiliate_link_present": "https://example.invalid"}]))
        self.assertEqual(result.observation, Observation.MALFORMED_RESPONSE)

    def test_m_missing_or_invalid_expected_content_id(self) -> None:
        missing = fixture()
        del missing["expected_content_id"]
        self.assertEqual(evaluate(missing).observation, Observation.MALFORMED_RESPONSE)
        self.assertEqual(evaluate(fixture(expected_content_id="bad/id")).observation, Observation.MALFORMED_RESPONSE)

    def test_n_unknown_fields_are_rejected(self) -> None:
        result = evaluate(fixture(raw_response={"secret": "value"}))
        self.assertEqual(result.observation, Observation.MALFORMED_RESPONSE)

    def test_o_internal_exception_returns_safe_unknown(self) -> None:
        class ExplodingMapping(Mapping[str, Any]):
            def __getitem__(self, key: str) -> Any:
                raise RuntimeError("boom")
            def __iter__(self) -> Iterator[str]:
                raise RuntimeError("boom")
            def __len__(self) -> int:
                raise RuntimeError("boom")

        result = evaluate(ExplodingMapping())
        self.assertEqual(result.observation, Observation.UNKNOWN)
        self.assertEqual(result.reason_codes, ("INTERNAL_EVALUATION_ERROR",))

    def test_contract_never_contains_business_decision_vocabulary(self) -> None:
        prohibited = {
            "SALE_ENDED",
            "UNPUBLISHED",
            "DELETED",
            "AFFILIATE_INELIGIBLE",
            "CONFIRMED_UNAVAILABLE",
            "CONFIRMED_AVAILABLE",
        }
        source = (ROOT / "scripts" / "product_verification.py").read_text(encoding="utf-8")
        for word in prohibited:
            self.assertNotIn(word, source)


if __name__ == "__main__":
    unittest.main()
