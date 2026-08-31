from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


class GitHubActionsCIContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = WORKFLOW.read_text(encoding="utf-8")

    def test_triggers_only_pull_requests_and_main_pushes(self):
        self.assertIn("  pull_request:\n", self.content)
        self.assertIn("  push:\n    branches:\n      - main\n", self.content)
        self.assertNotIn("schedule:", self.content)
        self.assertNotIn("workflow_dispatch:", self.content)

    def test_token_is_read_only(self):
        self.assertIn("permissions:\n  contents: read\n", self.content)
        self.assertNotRegex(self.content, r"(?m)^\s*[a-z-]+:\s*write\s*$")

    def test_standard_runner_has_timeout_and_concurrency(self):
        self.assertIn("runs-on: ubuntu-latest", self.content)
        self.assertIn("timeout-minutes: 5", self.content)
        self.assertIn("cancel-in-progress: true", self.content)
        self.assertNotIn("larger", self.content.lower())
        self.assertNotIn("self-hosted", self.content)

    def test_checkout_is_sha_pinned_without_persisted_credentials(self):
        match = re.search(r"uses: actions/checkout@([0-9a-f]{40})", self.content)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1),
                         "3d3c42e5aac5ba805825da76410c181273ba90b1")
        self.assertIn("persist-credentials: false", self.content)
        self.assertIn("fetch-depth: 1", self.content)

    def test_baseline_commands_are_exact_and_dependency_free(self):
        self.assertIn("run: python3 --version", self.content)
        self.assertIn("run: python3 -m compileall -q scripts tests", self.content)
        self.assertIn("run: python3 -m unittest discover -s tests", self.content)
        for forbidden in ("pip install", "curl ", "wget ", "npm ", "docker "):
            self.assertNotIn(forbidden, self.content)

    def test_no_secrets_artifacts_cache_deploy_or_mutation(self):
        lowered = self.content.lower()
        for forbidden in (
            "secrets.", "actions/upload-artifact", "actions/cache", "deploy",
            "release", "git push", "gh ", "pull-requests: write",
        ):
            self.assertNotIn(forbidden, lowered)


if __name__ == "__main__":
    unittest.main()
