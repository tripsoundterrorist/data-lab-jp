# Test Tiers v0.1

## Scope

This contract adds deterministic local entry points for three test tiers without
changing production runtime behavior or the existing baseline CI workflow.

## Tiers

- `FAST`: an explicit, reviewed manifest of high-signal coordinator, queue,
  persistence, collector, and CI contract tests.
- `REGRESSION`: every `tests/test_*.py` test discovered by `unittest`.
- `FULL`: compile every Python file under `scripts/` and `tests/`, then run the
  complete regression suite.

Run them from the repository root:

```text
python scripts/run_test_tier.py fast
python scripts/run_test_tier.py regression
python scripts/run_test_tier.py full
```

## Fail-closed rules

- Only the three fixed tier names are accepted.
- FAST manifest entries must be unique, use the `test_*.py` form, and exist.
- A compile failure stops FULL before tests run.
- Any failed test returns a non-zero process exit status.
- REGRESSION and FULL always use discovery, so new test files are included
  automatically and cannot be silently omitted from broad validation.

## Safety and cost boundary

This gate does not change LIVE state, approvals, queue writes, notification
writes, secrets, dependencies, runners, artifacts, or paid services. The
existing GitHub Actions baseline remains unchanged until tier equivalence is
validated in a separate small gate.
