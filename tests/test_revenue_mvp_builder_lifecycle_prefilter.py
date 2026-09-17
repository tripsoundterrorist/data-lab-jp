from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
from product_verification import Observation, VerificationObservation  # noqa: E402


spec = importlib.util.spec_from_file_location(
    "builder_lifecycle_prefilter", SCRIPTS / "build-public-data.py"
)
assert spec is not None and spec.loader is not None
builder = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = builder
spec.loader.exec_module(builder)


NOW = datetime(2026, 9, 16, 6, 0, tzinfo=timezone.utc)
PUBLIC_ID = "itm_0123456789abcdef01234567"
MASTER = {1: {"public_id": PUBLIC_ID}}
CONFIDENCE = {1: {"observation_stats": {"last_observed_at": NOW.isoformat()}}}


def observation(value, affiliate):
    expected = (
        True if value is Observation.API_ITEM_VISIBLE
        else False if value is Observation.API_ITEM_NOT_RETURNED
        else None
    )
    return VerificationObservation(
        value, NOW, expected, affiliate, 200, ("SANITIZED_RECEIPT",)
    )


def receipt(
    value=Observation.API_ITEM_VISIBLE,
    affiliate=True,
    *,
    inventory=builder.InventorySignal.UNKNOWN,
    fresh=True,
    public_id=PUBLIC_ID,
):
    return builder.LifecycleReceipt(
        builder.LIFECYCLE_RECEIPT_VERSION,
        public_id,
        observation(value, affiliate),
        inventory,
        fresh,
    )


def selected(*receipts):
    return builder.filter_master_items_by_lifecycle_receipts(
        MASTER, CONFIDENCE, tuple(receipts)
    )


class BuilderLifecyclePrefilterTests(unittest.TestCase):
    def test_exact_candidate_receipt_selects_item(self):
        items, excluded = selected(receipt())
        self.assertEqual(items, MASTER)
        self.assertEqual(excluded, 0)

    def test_missing_receipt_excludes_item(self):
        items, excluded = selected()
        self.assertEqual(items, {})
        self.assertEqual(excluded, 1)

    def test_duplicate_or_item_mismatch_fails_closed(self):
        with self.assertRaisesRegex(builder.PublicDataError, "DUPLICATE"):
            selected(receipt(), receipt())
        with self.assertRaisesRegex(builder.PublicDataError, "ITEM_MISMATCH"):
            selected(receipt(public_id="itm_ffffffffffffffffffffffff"))

    def test_nonvisible_missing_unknown_error_rate_limit_and_stale_exclude(self):
        cases = (
            receipt(Observation.API_ITEM_NOT_RETURNED, None),
            receipt(Observation.API_ITEM_VISIBLE, False),
            receipt(Observation.API_ITEM_VISIBLE, None),
            receipt(Observation.API_ERROR, None),
            receipt(Observation.API_RATE_LIMITED, None),
            receipt(fresh=False),
        )
        for value in cases:
            with self.subTest(observation=value.observation.observation):
                items, excluded = selected(value)
                self.assertEqual(items, {})
                self.assertEqual(excluded, 1)

    def test_preorder_and_out_of_stock_alone_do_not_exclude(self):
        for signal in (
            builder.InventorySignal.PREORDER,
            builder.InventorySignal.OUT_OF_STOCK,
        ):
            with self.subTest(signal=signal):
                items, excluded = selected(receipt(inventory=signal))
                self.assertEqual(items, MASTER)
                self.assertEqual(excluded, 0)

    def test_observation_timestamp_must_match_same_public_item(self):
        mismatched = builder.LifecycleReceipt(
            builder.LIFECYCLE_RECEIPT_VERSION,
            PUBLIC_ID,
            VerificationObservation(
                Observation.API_ITEM_VISIBLE,
                datetime(2026, 9, 16, 7, 0, tzinfo=timezone.utc),
                True,
                True,
                200,
                ("SANITIZED_RECEIPT",),
            ),
            builder.InventorySignal.UNKNOWN,
            True,
        )
        with self.assertRaisesRegex(builder.PublicDataError, "OBSERVATION_ITEM_MISMATCH"):
            selected(mismatched)

    def test_unknown_type_version_and_non_tuple_fail_closed(self):
        for value in (
            [],
            (None,),
            (builder.LifecycleReceipt("unknown", PUBLIC_ID, observation(Observation.API_ITEM_VISIBLE, True), builder.InventorySignal.UNKNOWN, True),),
        ):
            with self.subTest(value=value):
                with self.assertRaises(builder.PublicDataError):
                    builder.filter_master_items_by_lifecycle_receipts(
                        MASTER, CONFIDENCE, value
                    )

    def test_receipt_and_builder_surface_contain_no_raw_sensitive_fields(self):
        self.assertEqual(
            builder.LifecycleReceipt.__slots__,
            ("version", "public_id", "observation", "inventory_signal", "freshness_confirmed"),
        )
        source = (SCRIPTS / "revenue_mvp_lifecycle_receipt.py").read_text(encoding="utf-8")
        receipt_section = source.split("class LifecycleReceipt:", 1)[1].split("__all__", 1)[0]
        for forbidden in ("affiliate_url", "affiliateURL", "api_id", "affiliate_id", "raw_response"):
            self.assertNotIn(forbidden, receipt_section)

    def test_actual_builder_excludes_before_index_and_detail_generation(self):
        confidence_module = mock.Mock()
        confidence_module.calculate.return_value = {
            "score_version": "0.1",
            "items": [{"item_id": 1, **CONFIDENCE[1]}],
        }
        price_module = mock.Mock()
        price_module.calculate.return_value = {"version": "0.1", "items": [{"item_id": 1}]}
        full_master = {
            1: {
                "public_id": PUBLIC_ID,
                "title": "local fixture",
                "image_url": None,
                "item_url": None,
                "metadata": {key: [] for key in ("maker", "series", "actress", "genre")},
                "entity_maps": {key: {} for key in ("maker", "series", "actress", "genre")},
            }
        }
        with (
            mock.patch.object(builder, "load_analysis_module", side_effect=(confidence_module, price_module)),
            mock.patch.object(builder, "read_master_items", return_value=full_master),
        ):
            files, summary = builder.build_documents(Path("unused"), NOW, NOW)
        index = builder.json.loads(files["index.json"])
        manifest = builder.json.loads(files["manifest.json"])
        self.assertEqual(index["items"], [])
        self.assertFalse(any(path.startswith("items/") for path in files))
        self.assertEqual(manifest["publication_status"], "local_validation_only")
        self.assertEqual(manifest["item_count"], 0)
        self.assertTrue(summary["lifecycle_receipts_required"])
        self.assertEqual(summary["lifecycle_excluded_item_count"], 1)
        self.assertEqual(summary["sizes"]["detail_average_bytes"], 0)
        self.assertEqual(summary["sizes"]["detail_max_bytes"], 0)

    def test_actual_builder_emits_only_exact_candidate_with_cta_closed(self):
        confidence_module = mock.Mock()
        confidence_module.calculate.return_value = {
            "score_version": "0.1",
            "items": [{"item_id": 1, **CONFIDENCE[1]}],
        }
        price_module = mock.Mock()
        price_module.calculate.return_value = {
            "version": "0.1",
            "items": [{"item_id": 1, "current_price": 1000, "current_price_observed_at": NOW.isoformat()}],
        }
        full_master = {
            1: {
                "public_id": PUBLIC_ID,
                "title": "local fixture",
                "image_url": None,
                "item_url": None,
                "metadata": {key: [] for key in ("maker", "series", "actress", "genre")},
                "entity_maps": {key: {} for key in ("maker", "series", "actress", "genre")},
            }
        }
        confidence_public = {
            "score": 100,
            "label": {"code": "high", "en": "High", "ja": "高"},
            "version": "0.1",
            "components": {
                key: 100
                for key in (
                    "freshness", "observation_depth", "metadata_completeness",
                    "price_data", "temporal_confidence",
                )
            },
            "warnings": [],
        }
        price_public = {
            "version": "0.1",
            "observed_set_percentile": 50,
            "percentile_method": "fixture",
            "price_band": None,
            "genre_comparisons": [],
            "maker_comparison": {"available": False, "comparisons": []},
            "price_history": {
                "first_observed_price": 1000,
                "first_price_observed_at": NOW.isoformat(),
                "latest_observed_price": 1000,
                "latest_price_observed_at": NOW.isoformat(),
                "min_observed_price": 1000,
                "max_observed_price": 1000,
                "price_observation_count": 1,
                "distinct_price_observation_dates": 1,
                "price_observation_span_days": 0,
            },
            "warnings": [],
        }

        def confidence_view(_item, detailed):
            keys = builder.PUBLIC_ALLOWED_FIELDS[
                "confidence_detail" if detailed else "confidence_summary"
            ]
            return {key: confidence_public[key] for key in keys}

        def price_view(_item, _master, detailed):
            keys = builder.PUBLIC_ALLOWED_FIELDS[
                "price_detail" if detailed else "price_summary"
            ]
            return {key: price_public[key] for key in keys}

        with (
            mock.patch.object(builder, "load_analysis_module", side_effect=(confidence_module, price_module)),
            mock.patch.object(builder, "read_master_items", return_value=full_master),
            mock.patch.object(builder, "public_confidence", side_effect=confidence_view),
            mock.patch.object(builder, "public_price_analysis", side_effect=price_view),
        ):
            files, summary = builder.build_documents(
                Path("unused"), NOW, NOW, lifecycle_receipts=(receipt(),)
            )
        index = builder.json.loads(files["index.json"])
        detail = builder.json.loads(files[builder.detail_relative_path(PUBLIC_ID)])
        self.assertEqual([item["public_id"] for item in index["items"]], [PUBLIC_ID])
        self.assertEqual(detail["item"]["public_id"], PUBLIC_ID)
        self.assertIs(detail["item"]["affiliate_cta_eligible"], False)
        self.assertEqual(summary["lifecycle_excluded_item_count"], 0)


if __name__ == "__main__":
    unittest.main()
