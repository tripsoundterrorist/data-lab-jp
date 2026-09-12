# Temporal Active Runner Candidate Evidence v0.1

This bounded evidence runner verifies the isolated candidate in an OS-managed
temporary directory. It checks the approved design boundary, exact validated
four-population bundle, four successful dry assessments, four persisted files,
non-empty read-back, false production authorities, rejection before I/O for an
invalid bundle, and identifier-free safe output.

All eight checks currently pass. Filesystem access is limited to the temporary
test directory and is removed when the assessment exits. The evidence does not
connect the active pipeline and does not authorize API access, production or D1
writes, scheduler changes, deployment, publication, affiliate activation, or a
Cloudflare plan change.

`ISOLATED_ACTIVE_RUNNER_EVIDENCE_READY` is implementation evidence only. Active
connection remains a separate explicit approval Gate and is not required for
the Revenue MVP while the DMM Lifecycle and Sort response is pending.
