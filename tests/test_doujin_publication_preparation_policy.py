from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PREPARATION = ROOT / "docs/policies/doujin-publication-preparation-v0.1.md"
RETENTION = ROOT / "docs/policies/category-raw-retention-candidate-v0.1.md"


class DoujinPublicationPreparationPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.preparation = PREPARATION.read_text(encoding="utf-8")
        cls.retention = RETENTION.read_text(encoding="utf-8")

    def test_preparation_keeps_all_live_boundaries_closed(self):
        for field in (
            "publication_allowed", "affiliate_activation_allowed",
            "sitemap_change_allowed", "production_write_allowed",
        ):
            self.assertIn(field, self.preparation)
        self.assertIn("remain false", self.preparation)
        self.assertIn("no publication authorization", self.preparation)

    def test_entity_identity_is_not_inferred_from_names(self):
        self.assertIn("relabel it as `circle`", self.preparation)
        self.assertIn("Equal display names do not establish identity", self.preparation)

    def test_raw_retention_remains_unconfirmed_and_private(self):
        self.assertIn("UNCONFIRMED", self.retention)
        self.assertIn("outside public artifacts", self.retention)
        self.assertIn("Do not copy raw observations into D1", self.retention)
        self.assertIn("does not authorize", self.retention)

    def test_prohibited_shortcuts_are_not_authorized(self):
        combined = (self.preparation + self.retention).casefold()
        self.assertNotIn("publication_allowed=true", combined)
        self.assertNotIn("production_write_allowed=true", combined)
        self.assertNotIn("automatic deletion is allowed", combined)


if __name__ == "__main__":
    unittest.main()
