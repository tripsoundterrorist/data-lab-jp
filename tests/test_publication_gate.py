from __future__ import annotations

import copy
import importlib.util
import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from publication_gate import evaluate_publication_gate  # noqa: E402


PUBLIC_ID = "itm_0123456789abcdef01234567"
TIMESTAMP = "2026-08-23T06:00:00Z"


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, separators=(",", ":")) + "\n").encode("utf-8")


def artifact(
    publication_status: str = "public",
    rights: list[str] | None = None,
    schema: str = "0.1",
    policy: str = "0.1",
) -> dict[str, bytes]:
    index_item = {
        "public_id": PUBLIC_ID,
        "title": "Fixture title",
        "current_price": 1000,
        "last_observed_at": TIMESTAMP,
    }
    detail_item = copy.deepcopy(index_item)
    manifest = {
        "public_schema_version": schema,
        "public_policy_version": policy,
        "publication_status": publication_status,
        "rights_review_required": [] if rights is None else rights,
        "generated_at": TIMESTAMP,
        "as_of": TIMESTAMP,
        "item_count": 1,
    }
    index = {
        "public_schema_version": schema,
        "generated_at": TIMESTAMP,
        "as_of": TIMESTAMP,
        "items": [index_item],
    }
    detail = {
        "public_schema_version": schema,
        "generated_at": TIMESTAMP,
        "as_of": TIMESTAMP,
        "item": detail_item,
    }
    return {
        "manifest.json": json_bytes(manifest),
        "index.json": json_bytes(index),
        f"items/01/{PUBLIC_ID}.json": json_bytes(detail),
    }


def decoded(files: dict[str, bytes]) -> dict[str, object]:
    return {path: json.loads(content) for path, content in files.items()}


def encoded(documents: dict[str, object]) -> dict[str, bytes]:
    return {path: json_bytes(value) for path, value in documents.items()}


class PublicationGateTests(unittest.TestCase):
    def test_a_current_state_is_blocked(self) -> None:
        result = evaluate_publication_gate(
            artifact("local_validation_only", ["title", "image_url"])
        )
        self.assertFalse(result.eligible)
        self.assertIn("PUBLICATION_STATUS_NOT_PUBLIC", result.reasons)
        self.assertIn("RIGHTS_REVIEW_PENDING", result.reasons)

    def test_b_public_status_with_pending_rights_is_blocked(self) -> None:
        result = evaluate_publication_gate(artifact("public", ["title"]))
        self.assertFalse(result.eligible)
        self.assertEqual(result.reasons, ("RIGHTS_REVIEW_PENDING",))

    def test_c_empty_rights_with_local_status_is_blocked(self) -> None:
        result = evaluate_publication_gate(artifact("local_validation_only", []))
        self.assertFalse(result.eligible)
        self.assertEqual(result.reasons, ("PUBLICATION_STATUS_NOT_PUBLIC",))

    def test_d_all_publication_conditions_are_eligible(self) -> None:
        result = evaluate_publication_gate(artifact())
        self.assertTrue(result.eligible)
        self.assertEqual(result.status, "eligible")
        self.assertEqual(result.reasons, ())

    def test_e_unsupported_schema_is_blocked(self) -> None:
        result = evaluate_publication_gate(artifact(schema="9.9"))
        self.assertFalse(result.eligible)
        self.assertIn("UNSUPPORTED_SCHEMA_VERSION", result.reasons)

    def test_f_unsupported_policy_is_blocked(self) -> None:
        result = evaluate_publication_gate(artifact(policy="9.9"))
        self.assertFalse(result.eligible)
        self.assertIn("UNSUPPORTED_POLICY_VERSION", result.reasons)

    def test_g_forbidden_fields_are_blocked(self) -> None:
        for field in ("affiliate_url", "content_id", "query_context_json"):
            with self.subTest(field=field):
                documents = decoded(artifact())
                documents["index.json"]["items"][0][field] = "forbidden"
                result = evaluate_publication_gate(encoded(documents))
                self.assertFalse(result.eligible)
                self.assertIn("FORBIDDEN_FIELD_PRESENT", result.reasons)

    def test_h_secret_pattern_is_blocked(self) -> None:
        documents = decoded(artifact())
        documents["index.json"]["items"][0]["title"] = "api_id=fixture-secret"
        result = evaluate_publication_gate(encoded(documents))
        self.assertFalse(result.eligible)
        self.assertIn("SECRET_PATTERN_DETECTED", result.reasons)

    def test_i_missing_required_field_is_blocked(self) -> None:
        documents = decoded(artifact())
        del documents["index.json"]["items"][0]["title"]
        result = evaluate_publication_gate(encoded(documents))
        self.assertFalse(result.eligible)
        self.assertIn("REQUIRED_FIELD_MISSING", result.reasons)

    def test_j_malformed_public_id_and_timestamp_are_blocked(self) -> None:
        documents = decoded(artifact())
        documents["index.json"]["items"][0]["public_id"] = "bad-id"
        documents["index.json"]["items"][0]["last_observed_at"] = "not-a-time"
        result = evaluate_publication_gate(encoded(documents))
        self.assertFalse(result.eligible)
        self.assertIn("INVALID_PUBLIC_ID", result.reasons)
        self.assertIn("INVALID_TIMESTAMP", result.reasons)

    def test_k_nested_forbidden_field_is_blocked(self) -> None:
        documents = decoded(artifact())
        detail_path = f"items/01/{PUBLIC_ID}.json"
        documents[detail_path]["item"]["analysis"] = {
            "nested": {"content_id": "forbidden"}
        }
        result = evaluate_publication_gate(encoded(documents))
        self.assertFalse(result.eligible)
        self.assertIn("FORBIDDEN_FIELD_PRESENT", result.reasons)

    def test_l_casing_variations_are_blocked(self) -> None:
        for field in ("affiliateURL", "AffiliateUrl", "contentId", "queryContextJson"):
            with self.subTest(field=field):
                documents = decoded(artifact())
                documents["index.json"]["items"][0][field] = "forbidden"
                result = evaluate_publication_gate(encoded(documents))
                self.assertFalse(result.eligible)
                self.assertIn("FORBIDDEN_FIELD_PRESENT", result.reasons)

    def test_invalid_json_fails_closed(self) -> None:
        files = artifact()
        files["manifest.json"] = b"not-json"
        result = evaluate_publication_gate(files)
        self.assertFalse(result.eligible)
        self.assertIn("INVALID_PUBLIC_DOCUMENT", result.reasons)

    def test_internal_exception_fails_closed(self) -> None:
        class ExplodingMapping(dict[str, bytes]):
            def items(self):
                raise RuntimeError("fixture failure")

        result = evaluate_publication_gate(ExplodingMapping())
        self.assertFalse(result.eligible)
        self.assertEqual(result.reasons, ("INVALID_PUBLIC_DOCUMENT",))

    def test_unknown_status_fails_closed(self) -> None:
        result = evaluate_publication_gate(artifact("unknown", []))
        self.assertFalse(result.eligible)
        self.assertIn("PUBLICATION_STATUS_NOT_PUBLIC", result.reasons)

    def test_detail_public_id_mismatch_fails_closed(self) -> None:
        documents = decoded(artifact())
        detail_path = f"items/01/{PUBLIC_ID}.json"
        documents[detail_path]["item"]["public_id"] = (
            "itm_ffffffffffffffffffffffff"
        )
        result = evaluate_publication_gate(encoded(documents))
        self.assertFalse(result.eligible)
        self.assertIn("INVALID_PUBLIC_DOCUMENT", result.reasons)

    def test_local_validation_artifact_is_not_mutated(self) -> None:
        files = artifact("local_validation_only", ["title"])
        before = copy.deepcopy(files)
        result = evaluate_publication_gate(files)
        self.assertFalse(result.eligible)
        self.assertEqual(files, before)


class BuilderBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        path = SCRIPTS / "build-public-data.py"
        specification = importlib.util.spec_from_file_location("public_builder", path)
        assert specification is not None and specification.loader is not None
        cls.builder = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(cls.builder)

    def test_production_mode_blocks_before_write(self) -> None:
        files = artifact("local_validation_only", ["title"])
        with (
            mock.patch.object(self.builder, "build_documents", return_value=(files, {})),
            mock.patch.object(self.builder, "load_secret_values", return_value=[]),
            mock.patch.object(self.builder, "atomic_write") as writer,
            redirect_stdout(io.StringIO()),
        ):
            exit_code = self.builder.main(["--publication-mode", "production", "--json"])
        self.assertEqual(exit_code, 2)
        writer.assert_not_called()

    def test_local_validation_mode_keeps_local_write_workflow(self) -> None:
        files = artifact("local_validation_only", ["title"])
        with (
            mock.patch.object(self.builder, "build_documents", return_value=(files, {})),
            mock.patch.object(self.builder, "load_secret_values", return_value=[]),
            mock.patch.object(self.builder, "atomic_write") as writer,
            redirect_stdout(io.StringIO()),
        ):
            exit_code = self.builder.main(["--publication-mode", "local-validation", "--json"])
        self.assertEqual(exit_code, 0)
        writer.assert_called_once()


if __name__ == "__main__":
    unittest.main()
