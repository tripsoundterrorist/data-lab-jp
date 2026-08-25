# DATA LAB Publication Readiness Report v0.1

`report_version=0.1`。本reportは既存Gate、Rights Decision Matrix、Official Blocker Registry、Data Policyのread-only集約であり、公開を許可または実行する機能ではない。

## Current result

- Rights Gate: `PASS`
- Data Policy Gate: `PASS`
- Lifecycle Gate: `PENDING_OFFICIAL_CONFIRMATION`
- Semantics Gate: `PENDING_OFFICIAL_CONFIRMATION`
- Publication Status Gate: `CLOSED`
- `overall_eligible=false`
- `overall_readiness=BLOCKED`

安全な要約は、**RIGHTS CLEARED / DATA POLICY CLEARED / OFFICIAL SEMANTICS AND LIFECYCLE CONFIRMATION PENDING / PUBLICATION NOT ACTIVATED**である。

## Aggregation rules

`READY`はPublication Gate由来の`overall_eligible=true`に加え、全required gateがPASS、公式blockerがRESOLVED、Publication ActivationがRESOLVED、`publication_status=public`という整合した入力でのみ返す。矛盾、未知Gate・blocker・version、unsafe inputは`FAIL_CLOSED`とする。

Rights summaryはdecision件数とsafe field名を表示するが、secret-bearing field名はredactする。Rights approvalは他Gateを上書きしない。

Temporal sectionはDay 1 baseline、Day 2 comparison、history count、`NOT_EVALUATED`を観測情報としてのみ表示する。popularity、sales、market trend、production readinessへ変換しない。

## Current blockers and next actions

1. `WAIT_FOR_DMM_LIFECYCLE_RESPONSE`
2. `WAIT_FOR_DMM_SORT_SEMANTICS_RESPONSE`
3. `CONTINUE_TEMPORAL_OBSERVATION`
4. `PREPARE_PUBLICATION_ARTIFACT_VALIDATION`

内部検証は公式回答の代替にならない。Publication Activationにはrequired gates、artifact validation、production build、deployment preflight、別commitによるstatus変更、明示的内部承認が必要である。

safe outputにはcredential、API/affiliate ID、raw support email、raw API response、content/anonymous ID、商品タイトル、absolute path、traceback、raw exceptionを含めない。
