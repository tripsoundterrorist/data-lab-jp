import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_minimal_opaque_go_cta_contract as contract  # noqa: E402


PUBLIC_ID = "itm_0123456789abcdef01234567"


def candidate(**changes):
    value = {
        "contract_version": contract.VERSION,
        "public_id": PUBLIC_ID,
        "cta_href": f"/go/{PUBLIC_ID}",
        "disclosure_text": contract.DISCLOSURE,
        "disclosure_proximate": True,
        "affiliate_url_exposed": False,
        "server_side_lookup_required": True,
        "rate_limit_required": True,
        "publication_scope_expanded": True,
        "exact_unordered_scope_unchanged": True,
    }
    value.update(changes)
    return value


class MinimalOpaqueGoCtaContractTests(unittest.TestCase):
    def test_exact_candidate_is_review_only(self):
        result = contract.review(candidate())
        self.assertEqual(result.status, contract.READY)
        self.assertTrue(result.eligible_for_implementation_review)
        self.assertTrue(result.public_id_accepted)
        self.assertTrue(result.same_origin_route_accepted)
        self.assertTrue(result.disclosure_accepted)
        self.assertFalse(result.publication_allowed)
        self.assertFalse(result.production_activation_allowed)
        self.assertFalse(result.affiliate_eligibility_allowed)
        self.assertFalse(result.gate_mutation_allowed)
        self.assertFalse(result.deployment_allowed)

    def test_every_boundary_fails_closed(self):
        cases = (
            {"public_id": "content-id"},
            {"cta_href": "https://example.invalid"},
            {"disclosure_text": "FANZAで確認"},
            {"disclosure_proximate": False},
            {"affiliate_url_exposed": True},
            {"server_side_lookup_required": False},
            {"rate_limit_required": False},
            {"publication_scope_expanded": False},
            {"exact_unordered_scope_unchanged": False},
        )
        for changes in cases:
            with self.subTest(changes=changes):
                result = contract.review(candidate(**changes))
                self.assertEqual(result.status, contract.BLOCKED)
                self.assertFalse(result.deployment_allowed)

    def test_unknown_fields_and_hostile_values_are_not_exposed(self):
        value = candidate(secret="private-marker")
        result = contract.review(value)
        self.assertEqual(result.status, contract.BLOCKED)
        self.assertNotIn("private-marker", json.dumps(result.to_dict()))


if __name__ == "__main__":
    unittest.main()
