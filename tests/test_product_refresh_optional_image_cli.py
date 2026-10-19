"""Manual image omission is explicit and never enabled by default."""
from contextlib import redirect_stdout
import io
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import revenue_mvp_product_refresh_candidate as candidate
import revenue_mvp_product_refresh_preapproval as preapproval
import revenue_mvp_product_refresh_rehearsal as rehearsal


class OptionalImageCliTests(unittest.TestCase):
    def test_manual_clis_default_off_and_forward_explicit_opt_in(self):
        common = ["--db", "fixture.db", "--expected-count", "100"]
        build = common + ["--expected-db-sha256", "0" * 64,
                          "--evaluated-at", "2026-09-30T01:00:00Z",
                          "--output", "candidate.html"]
        cases = (
            (candidate, "build_candidate", build, candidate.READY),
            (rehearsal, "assess", common + ["--source", "current.html"],
             "READY_FOR_SEPARATE_REFRESH_CANDIDATE"),
            (preapproval, "assess", build + ["--source", "current.html",
             "--d1-export", "fixture.sql", "--expected-d1-sha256", "0" * 64],
             preapproval.READY),
        )
        for module, method, argv, ready in cases:
            for enabled in (False, True):
                with self.subTest(module=module.__name__, enabled=enabled):
                    result = SimpleNamespace(status=ready, to_dict=lambda: {})
                    with patch.object(module, method, return_value=result) as invoke:
                        with redirect_stdout(io.StringIO()):
                            code = module.main(argv + (["--allow-missing-images"] if enabled else []))
                    self.assertEqual(code, 0)
                    self.assertIs(invoke.call_args.kwargs["allow_missing_images"], enabled)
                    self.assertEqual(invoke.call_args.kwargs["expected_count"], 100)


if __name__ == "__main__":
    unittest.main()
