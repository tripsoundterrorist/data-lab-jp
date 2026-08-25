# DATA LAB Temporal Probe Day 3+ Runbook v0.1

## Scope and safety

This runbook fixes the Day 3 and later observational workflow. It does not authorize API communication, state mutation, database writes, publication changes, deployment, or automatic deletion. Temporal evidence never unlocks the Lifecycle, Semantics, or Publication Gate and never resolves an Official Blocker.

## Timeline and target window

- Day 1 baseline: approximately 2026-08-24 23:28:30 JST, four states.
- Day 2 comparison: approximately 2026-08-25 23:34:23 JST, four states; `history_count = 1`.
- Day 3 recommended window: 2026-08-26 23:29–23:40 JST. Recalculate from each actual Day 2 `captured_at`; 12–48 hours is mandatory and approximately 24 hours, preferably ±15 minutes, is preferred.
- Successful Day 3: `history_count = 2`, `classification = OBSERVATION_ONLY`, `production_readiness = NOT_EVALUATED`.
- Successful Day 4: `history_count = 3`, `production_readiness = REVIEW_ELIGIBLE`. This requires manual review and is not READY, production-ready, a Gate unlock, or collection-policy eligibility.

## Mandatory preflight

Stop before API communication unless every check passes: Git is clean; local `main` equals `origin/main`; running native and related processes are zero; today's Collector, Backup, and Stale Check completed normally; database integrity and foreign keys are OK; Day 1/Day 2 states validate; the latest previous state is unique for every population; the state directory is writable; the fixed-plan dry-run succeeds without filesystem changes; and every interval is within policy. Never rerun scheduled tasks as part of this procedure.

Record the database SHA-256/counts, Git HEAD/status, and filename/SHA-256 for all existing states before execution. Do not expose anonymous item IDs.

## Fixed execution contract

Use only these ordered populations with `site=FANZA`, `service=digital`, `floor=videoa`, `hits=100`:

1. `rank`, offset 1
2. `rank`, offset 101
3. `review`, offset 1
4. `review`, offset 101

Use retry 0, stop on the first error, and at least one second between requests. The only permitted chain is Orchestrator → Adapter → Runner → State Store → comparison → Stability Policy → Assessment Pipeline. Do not implement independent comparison calculations.

## Completion and safe reporting

Day 3 succeeds only when all four API calls succeed, all four states are saved, all four comparisons are available, all four intervals are valid, all four assessments are valid, database/Git/previous states remain unchanged, and there is no rate limit, error, or anomaly.

Report each population separately: interval hours, retained, entered, exited, retention, entry/exit rates, Jaccard, turnover, observation band, classification, and production readiness. Never average populations or combine rank and review. The observation band describes query-population composition retention only; never label Day 3 STABLE, UNSTABLE, READY, or PRODUCTION_READY.

## Failure and state handling

Fail closed on previous-state ambiguity, malformed state, interval anomaly, API/rate-limit/response error, Runner or Store failure, assessment anomaly, database mutation, unexpected Git diff, or internal exception. On partial failure, preserve successful states, do not roll back, stop remaining work, and require manual follow-up.

Successful states are local-only and Git-ignored. Retention v0.1 remains `HOT_RETENTION_DAYS = 45`; Day 1, Day 2, and Day 3 are `KEEP_HOT`. No automatic deletion is authorized.

## Post-run verification

Recheck database SHA-256/counts, Git cleanliness, prior-state filename/SHA-256 values, new-state validation, process counts, and production files. Any unexpected mutation invalidates completion and requires manual review. Publication status and all publication/blocker policies must remain unchanged.
