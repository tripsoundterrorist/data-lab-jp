# Revenue MVP Preconnection Decode Official Intake v0.1

This pure local contract prepares for possible official Q1/Q3 answers. No
inquiry is sent, and no answer is presumed. It classifies only two sanitized
question states:

- `OUTPUT_JSON_SUCCESS_RESULT_STATUS_NUMERIC_200`: whether a normal product
  retrieval with `output=json` is officially specified to carry `result.status`
  as the JSON number 200.
- `SUCCESS_CONTENT_TYPE_JSON_UTF8_INCLUDING_CHARSET_OMISSION`: whether a normal
  response is officially specified as JSON with UTF-8 encoding, including the
  case in which a charset is omitted. `YES` requires explicit support for the
  whole compound question; a partial answer is `AMBIGUOUS` or `UNSPECIFIED`.

Input is one exact built-in dictionary with only `intake_version` (`0.1`),
`source_type`, `source_authority`, and `question_states`. The source pair is
either `DIRECT_SUPPORT_CONFIRMATION` / `DMM_AFFILIATE_SUPPORT` or
`OFFICIAL_DOCUMENTATION` / `DMM_OFFICIAL_DOCUMENTATION`. `question_states` must
be an exact built-in dictionary containing exactly the two question IDs, each
mapped to an exact string `YES`, `NO`, `UNSPECIFIED`, `AMBIGUOUS`, or
`CONTRADICTORY`. These are operator-provided classifications for later review,
not proof that a statement is official.

Missing or unknown fields, wrong version, nonofficial source, invalid state,
unanswered question, ambiguity, and contradiction return `BLOCKED` with a
fixed reason. Two explicit `YES` or `NO` states return
`SEPARATE_COMPLIANCE_REVIEW_REQUIRED`. A `NO` records an explicit negative
answer; it never grants the proposed decode behavior.

Every result keeps `live_connection_allowed=false`, `gate_unlock_allowed=false`,
`live_decode_profile_approved=false`, and
`explicit_connection_approval_required=true`. Separate Compliance review and
explicit connection approval remain necessary after any official answer. The
contract accepts and emits no raw answer, account, inquiry ID, API or affiliate
ID, URL, header value, credential, payload, or exception detail.

The September 12 Lifecycle/Sort intake and September 23 Q4/Q5 submission
status and intake are independent and unchanged. This module reads no file or
credential, executes no API request, writes no DB or artifact, sends no
message, and changes no production route, CTA, scheduler, eligibility, Gate,
deployment, or publication state.
