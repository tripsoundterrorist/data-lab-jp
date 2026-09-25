from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_minimal_opaque_go_cta_activation_review as subject  # noqa: E402
import revenue_mvp_minimal_opaque_go_cta_artifact_preflight as artifact  # noqa: E402
import revenue_mvp_minimal_opaque_go_cta_contract as contract  # noqa: E402
import revenue_mvp_minimal_opaque_go_cta_packet as packet  # noqa: E402
import revenue_mvp_minimal_opaque_go_cta_renderer as renderer  # noqa: E402


DIGEST = "f273ec05089eabd19da50e7d62dfb2f747282f53d37f9babcb7a63c79c78dcf9"


def evidence(**changes):
    value = {
        "contract_status": contract.READY,
        "packet_status": packet.READY,
        "renderer_status": renderer.READY,
        "artifact_preflight_status": artifact.PASS,
        "artifact_sha256": DIGEST,
        "runtime_deployment_preflight_status": "READY_FOR_DEPLOYMENT_REVIEW",
        "compliance_approved_artifact_sha256": DIGEST,
        "explicit_user_activation_approval": False,
    }
    value.update(changes)
    return value


class MinimalOpaqueGoCtaActivationReviewTests(unittest.TestCase):
    def test_exact_evidence_only_readies_explicit_review_request(self):
        result = subject.review(evidence())
        self.assertEqual(result.status, subject.READY)
        self.assertTrue(result.ready_to_request_explicit_activation_review)
        self.assertTrue(result.explicit_user_activation_approval_required)
        self.assertFalse(result.approval_granted)
        self.assertEqual(result.artifact_sha256, DIGEST)
        self.assertTrue(all(not getattr(result, field) for field in (
            "publication_allowed", "production_activation_allowed",
            "affiliate_eligibility_allowed", "gate_mutation_allowed",
            "d1_write_allowed", "deployment_allowed", "api_request_allowed",
        )))

    def test_each_missing_or_invalid_evidence_blocks(self):
        cases = (
            {"contract_status": "BLOCKED"},
            {"packet_status": "BLOCKED"},
            {"renderer_status": "BLOCKED"},
            {"artifact_preflight_status": "BLOCKED"},
            {"artifact_sha256": "invalid"},
            {"runtime_deployment_preflight_status": "BLOCKED"},
            {"compliance_approved_artifact_sha256": "0" * 64},
        )
        for changes in cases:
            with self.subTest(changes=changes):
                result = subject.review(evidence(**changes))
                self.assertEqual(result.status, subject.BLOCKED)
                self.assertFalse(result.ready_to_request_explicit_activation_review)
                self.assertFalse(result.deployment_allowed)

    def test_approval_cannot_be_preconsumed_or_inferred(self):
        for value in (True, None, 1, "approved"):
            with self.subTest(value=value):
                result = subject.review(evidence(explicit_user_activation_approval=value))
                self.assertEqual(result.status, subject.BLOCKED)
                self.assertFalse(result.approval_granted)

    def test_unknown_fields_and_non_dict_fail_closed(self):
        self.assertEqual(subject.review(None).status, subject.BLOCKED)
        value = evidence(secret="private")
        result = subject.review(value)
        self.assertEqual(result.status, subject.BLOCKED)
        self.assertNotIn("private", str(result.to_dict()))


if __name__ == "__main__":
    unittest.main()
