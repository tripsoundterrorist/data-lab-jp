from dataclasses import replace
import inspect
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import affiliate_cta_presentation as presentation  # noqa: E402
import ui_security_disclosure_policy as ui_policy  # noqa: E402


def passing_ui_result() -> ui_policy.UISecurityResult:
    return ui_policy.UISecurityResult(
        policy_version=ui_policy.POLICY_VERSION,
        ui_security_status=ui_policy.UI_SECURITY_PASS,
        render_allowed=True,
        disclosure_required=True,
        external_indicator_required=True,
        required_rel_tokens=tuple(sorted(ui_policy.AFFILIATE_REL)),
        prohibited_pattern_codes=(),
        reason_codes=("UI_SECURITY_REQUIREMENTS_SATISFIED",),
    )


class AffiliateCtaPresentationTests(unittest.TestCase):
    def test_allowed_result_shows_cta_and_disclosure_together(self):
        result = presentation.build_affiliate_cta(
            presentation_version=presentation.PRESENTATION_VERSION,
            ui_security_result=passing_ui_result(),
        )

        self.assertEqual(result.status, presentation.CTA_READY)
        self.assertTrue(result.cta_visible)
        self.assertTrue(result.disclosure_visible)
        self.assertEqual(result.cta_visible, result.disclosure_visible)
        self.assertIn("外部サイト", result.cta_label)
        self.assertTrue(result.disclosure_text.startswith("PR："))
        self.assertIn("アフィリエイトリンク", result.disclosure_text)
        self.assertEqual(
            set(result.required_rel_tokens),
            {"noopener", "noreferrer", "sponsored"},
        )
        self.assertTrue(result.external_indicator_visible)

    def test_blocked_upstream_hides_cta_and_all_presentation_text(self):
        blocked = replace(
            passing_ui_result(),
            ui_security_status=ui_policy.BLOCKED_UPSTREAM,
            render_allowed=False,
        )

        result = presentation.build_affiliate_cta(
            presentation_version=presentation.PRESENTATION_VERSION,
            ui_security_result=blocked,
        )

        self.assertEqual(result.status, presentation.CTA_HIDDEN)
        self.assertFalse(result.cta_visible)
        self.assertFalse(result.disclosure_visible)
        self.assertIsNone(result.cta_label)
        self.assertIsNone(result.disclosure_text)
        self.assertEqual(result.required_rel_tokens, ())
        self.assertFalse(result.external_indicator_visible)

    def test_pass_without_affiliate_security_requirements_is_rejected(self):
        for changes in (
            {"disclosure_required": False},
            {"external_indicator_required": False},
            {"required_rel_tokens": ("noopener", "noreferrer")},
            {"prohibited_pattern_codes": ("HIDDEN_DISCLOSURE",)},
        ):
            with self.subTest(changes=changes):
                result = presentation.build_affiliate_cta(
                    presentation_version=presentation.PRESENTATION_VERSION,
                    ui_security_result=replace(passing_ui_result(), **changes),
                )
                self.assertEqual(result.status, presentation.INVALID_INPUT)
                self.assertFalse(result.cta_visible)
                self.assertFalse(result.disclosure_visible)

    def test_invalid_object_and_version_fail_closed(self):
        invalid_object = presentation.build_affiliate_cta(
            presentation_version=presentation.PRESENTATION_VERSION,
            ui_security_result={"render_allowed": True},
        )
        self.assertEqual(invalid_object.status, presentation.INVALID_INPUT)
        self.assertFalse(invalid_object.cta_visible)

        invalid_version = presentation.build_affiliate_cta(
            presentation_version="999",
            ui_security_result=passing_ui_result(),
        )
        self.assertEqual(invalid_version.status, presentation.INVALID_INPUT)
        self.assertFalse(invalid_version.cta_visible)

    def test_contract_accepts_no_url_or_item_identifier(self):
        parameters = inspect.signature(
            presentation.build_affiliate_cta
        ).parameters
        self.assertEqual(
            set(parameters),
            {"presentation_version", "ui_security_result"},
        )

        result = presentation.build_affiliate_cta(
            presentation_version=presentation.PRESENTATION_VERSION,
            ui_security_result=passing_ui_result(),
        )
        output = json.dumps(result.to_dict(), ensure_ascii=False)
        self.assertNotIn("https://", output)
        self.assertNotIn("public_id", output)
        self.assertNotIn("content_id", output)


if __name__ == "__main__":
    unittest.main()
