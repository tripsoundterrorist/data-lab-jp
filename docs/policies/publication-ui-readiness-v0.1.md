# DATA LAB Publication UI Integration Readiness v0.1

## Scope

This pure/read-only policy integrates safe results from Affiliate Link Policy, Affiliate Link Adapter, Affiliate UI Handoff, and UI Security & Disclosure. For each component it validates a known version, exact contract, safe output, and cross-layer consistency. It never accepts URLs or item data and never changes a Gate, Official Blocker, lifecycle/semantics state, publication status, Public Data, or UI.

## Readiness

States are `BLOCKED`, `INTERNALLY_READY`, `PRODUCTION_CANDIDATE`, `INVALID_INPUT`, and `MANUAL_REVIEW_REQUIRED`. Validated four-layer contracts can set `all_internal_components_ready=true` while official blockers remain pending. `INTERNALLY_READY` is not production-ready or publication permission. `PRODUCTION_CANDIDATE` is not deployment approval or a Gate unlock.

The current closed Publication Gate plus pending Lifecycle and Semantics produces `overall_readiness=BLOCKED`, `all_internal_components_ready=true`, and `production_integration_allowed=false`. A fixture reaches `PRODUCTION_CANDIDATE` only when Gate is PASS, both official statuses are RESOLVED, and every delegated downstream render flag is already true.

## Contradictions and safe output

Policy-blocked with an Adapter candidate, Adapter production blocked with Handoff allowed, Handoff blocked with Security allowed, contradictory flags, or Security PASS attempting to bypass an official blocker requires `MANUAL_REVIEW_REQUIRED`. No state is inferred or updated.

Output is limited to readiness version, overall readiness, internal-component flag, production-integration flag, three upstream statuses, component statuses, and deterministic reason codes. URLs, titles, IDs, credentials, paths, raw Public Data, and exceptions are rejected or absent.

For each version 0.1 component, status enums, reason codes, and their boolean flags are checked against explicit allowlists and consistency rules. Unknown values fail closed as `INVALID_INPUT` and cannot become a production candidate.
