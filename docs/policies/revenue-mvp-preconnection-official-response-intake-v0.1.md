# Revenue MVP Preconnection Official Response Intake v0.1

This pure local contract classifies a sanitized observation of official answers
to the two preconnection questions recorded in the follow-up status:
`LIVE_SINGLE_REQUEST_PERMISSION` and `USER_AGENT_REQUIREMENT`. It does not read
the inquiry, a message, account information, an inquiry ID, API or affiliate
IDs, a URL, credentials, or an exception. No raw answer text belongs in this
contract, its tests, or its output.

Input is one exact built-in dictionary with only `intake_version` (`0.1`),
`source_type`, `source_authority`, and `question_states`. The source pair must
be `DIRECT_SUPPORT_CONFIRMATION` / `DMM_AFFILIATE_SUPPORT` or
`OFFICIAL_DOCUMENTATION` / `DMM_OFFICIAL_DOCUMENTATION`. `question_states` is an
exact built-in dictionary with exactly the two question IDs. Each state must
be an exact string: `YES`, `NO`, `UNSPECIFIED`, `AMBIGUOUS`, or `CONTRADICTORY`.
`YES` or `NO` describes the explicit official answer; neither is inferred from
silence. For Q5, `YES` means a user-agent requirement was stated, without
accepting or returning the actual user-agent string.

Missing, unknown, malformed, ambiguous, contradictory, or unspecified input
returns `BLOCKED` with a fixed reason code. Both questions explicitly answered
`YES` or `NO` return `SEPARATE_COMPLIANCE_REVIEW_REQUIRED`. A Q4 `NO` is an
explicit denial and does not grant a live request. All results set
`live_connection_allowed=false` and `gate_unlock_allowed=false`; separate
Compliance review and explicit connection approval remain required even when
both answers are explicit.

This contract does not overwrite the existing September 12 Lifecycle/Sort
intake or the September 23 preconnection submission status. It makes no live
request, reads no credential or file, writes no DB or artifact, sends no
message, and changes no production route, CTA, affiliate eligibility, Gate,
deployment, schedule, or publication state.
