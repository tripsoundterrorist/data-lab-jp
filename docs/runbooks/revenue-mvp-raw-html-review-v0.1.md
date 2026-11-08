# Raw HTML review preparation (local only)

## Decision

Keep Cloudflare Browser Integrity Check enabled. Do not spoof a browser user
agent, add exceptions, disable protection, or replay authenticated cookies.
The observed Python GET blocks establish BIC involvement for those requests,
not a general outage or a diagnosis of every possible 403.

Official reference: https://developers.cloudflare.com/waf/tools/browser-integrity-check/

## Implemented boundary

`scripts/revenue_mvp_raw_html_review.py` is a pure offline comparator, not an
acquisition adapter. It checks supplied UTF-8 raw response bytes, fixed URL,
200 status, content type, bounded size, a 15-minute claimed observation window,
and one of the two pinned HTML hashes. Only CR/LF normalization is permitted.
DOM serialization, screenshots, copied text, redirects and compressed wire
bodies are not valid inputs. Metadata supplied by a caller is not authenticated.

A matching result is `SUPPLIED_RESPONSE_MATCH_NOT_TRUSTED_CAPTURE`. It never
constructs the existing private capture type or feeds a current-state/release
path. All publication, Gate and eligibility authority remains false.
Tests use repository bytes as fixtures, not as live-production evidence.

## Still required before integration

1. Identify an approved browser/transport interface that exposes the original
   main-document response body and its bound request URL, final URL, status,
   content type, decoding state and actual observation time. Rendered DOM is
   not a substitute. Current browser tooling has not established this capability.
2. Implement and review that provenance adapter separately, with no credentials,
   no header impersonation, no security bypass and no automatic requests.
   Reject subresources, redirects, oversized bodies and stale/mismatched data.
3. Test tampering, replay, misbound metadata and failure paths before proposing
   an explicit change to the existing trusted capture mechanism. Never import
   a manually supplied matching hash as trusted evidence.
4. Review current item eligibility separately. A display hash, old API evidence,
   or a successful browser view does not establish present sale eligibility.

PR #414 stays on hold. This work does not authorize capture, private-key access,
new API calls, persistence of real data, publication, DB writes, push or merge.

## Proposed HAR review design (2026-10-15; not implemented)

### What HAR can and cannot prove

Chrome's sanitized export excludes sensitive headers such as Cookie,
Set-Cookie and Authorization. This is a reduction in risk, not a guarantee that
URLs, bodies, extensions, comments or other headers contain no private data.
Never ask the owner to attach an unreviewed HAR to chat, Git or a third-party
HAR viewer. Do not enable export with sensitive data.

HAR content.text may be HTTP-decoded, decompressed, unchunked and transcoded to
UTF-8; optional content.encoding can describe base64 representation. Thus HAR
does not universally preserve original wire bytes. An export is editable and
does not authenticate its URL, time, status or claimed network origin. A local
file hash or a local signature cannot repair that missing origin provenance.

Sources checked for this design:

- https://developer.chrome.com/docs/devtools/network/reference/#save-as-har
- https://webperfwg.org/specs/HAR/Overview.html (content section)

### Future workflow, only after separate capture approval

1. Agree on a browser/exporter version and a capture procedure first. Use only
   the public fixed page, no dashboard/login/API/go routes, no credential entry,
   no protection changes, and no User-Agent changes. An isolated unsigned-in
   browser context is a future proposal, not permission to create or use it now.
2. Owner exports only the single main-document request as sanitized HAR. Do not
   capture general browsing or admin sessions. Filtering must be verified; never
   assume a displayed filter guarantees the saved file contains only that row.
3. Owner keeps the file outside Git/cloud-sync/chat. A separately approved local
   validator may read only the explicitly selected file; no folder search,
   upload, network access, private-key access, persistence, or deletion.
4. Validator processes in memory and emits only a fixed reason code and safe
   aggregate receipt. No response text, URL supplied by the file, header values,
   paths, IPs, cookies, user identifiers, tracebacks or raw JSON are printed.
   Do not claim Python memory can be securely erased after processing.
5. Rejected originals remain under owner control. Do not automatically rewrite,
   quarantine or delete them. Any retention or cleanup needs separate scope.

### Proposed parser contract

Pure bytes-in/receipt-out function; no CLI, browser or existing Gate integration
in the first implementation. Initial conservative limits: UTF-8 JSON <=2 MiB,
nesting <=16, exactly one log.entries entry, decoded HTML <=1 MiB. Reject
duplicate JSON keys, NaN/Infinity, malformed Unicode, unexpected value types,
invalid base64 and unsupported exporter variants. Reject oversized input before
JSON parsing and bound nesting before recursive parsing; limits are not a claim
that arbitrary JSON parsing has no resource risk.

Use an explicit, versioned allowlist for the entire sanitized envelope, not only
the selected entry. Unknown extension fields fail closed. Validate primitive
types and lengths before examining content. No general-purpose HAR renderer,
HTML execution, external resource loading or URL opening is permitted.

Require all of the following in the accepted exporter profile:

- Request: exact GET and exact `https://datalabx.jp/items/`, with no userinfo,
  query, fragment or port variation; no request body, cookies or authorization.
- Response: integer 200, empty redirectURL, no redirects/304/cache reuse or
  service-worker origin. A single HAR entry alone does not prove no earlier
  redirect or service worker. Missing provenance markers or unsupported exporter
  semantics mean `HAR_PROVENANCE_UNCONFIRMED`, not an invented false value.
- Header names: bounded case-insensitive allowlist with no duplicate or
  conflicting values. Permit only explicitly necessary metadata (initially
  Content-Type and Content-Encoding); cookies, authorization, referrers and
  unknown/custom headers reject. Safe output never includes header values.
- Body: present content.text, UTF-8 HTML, optional strictly validated base64.
  Require agreement between MIME/charset declarations and exporter profile.
  Missing/omitted/truncated body fails closed; never refetch it automatically.
- Time: explicit offset-aware startedDateTime, finite nonnegative duration and
  separately supplied evaluation time. Require claimed start through completion
  to fit within 15 minutes before evaluation, not the file modification time.
  These remain untrusted claimed times and cannot establish authenticity.
- Expected digest: selected by the caller from pinned reviewed hashes, never
  accepted from HAR. Compare only UTF-8 bytes with the existing CR/LF
  normalization; no HTML parsing/reserialization, whitespace repair or DOM copy.

HAR Content-Encoding and HAR content.encoding are different layers. Do not
double-decompress content.text because a retained HTTP header says gzip/br.
Do not pass decoded HAR text to the existing raw-response comparator by falsely
changing HTTP Content-Encoding to identity or labelling it http_response_body.
Implement separate explicit HAR decoding semantics and a separate result type.
Any future bridge needs its own review; existing trusted capture remains intact.

An allowlisted exporter profile has not yet been demonstrated. It may be unable
to establish cache/service-worker/redirect provenance. That is an acceptable
blocked outcome, not a reason to relax the contract or request sensitive export.

### Result and acceptance tests

Successful comparison status: `MANUAL_HAR_CONTENT_MATCH_UNVERIFIED_PROVENANCE`.
Allow only schema version, fixed status/reason enums, allowlisted matched digest,
and boolean match flags in its output. Unknown-body hashes are not exported.
Keep trusted_public_capture, current_eligibility_verified, publication_allowed,
gate_mutation_allowed and database_write_performed false. The receipt must be
rejected by existing trusted-capture/release paths even if every comparison
matches. Never instantiate their private token-bearing observation type.

Before any real-file use, test synthetic fixtures only:

- Exact UTF-8 text/base64 matches and CRLF normalization; all authority false.
- Body change, DOM serialization, missing/truncated body, wrong expected digest.
- Wrong URL, multiple entries, duplicate keys/headers, redirects, 304, cache,
  service-worker and absent exporter provenance markers.
- Secrets in headers/cookies/query/postData/comments/unknown extensions; reject
  with generic codes and assert no fixture secret reaches stdout/stderr/results.
- Oversized input/decode, deep JSON, invalid base64/Unicode, gzip double-decode,
  conflicting MIME, NaN/Infinity, stale/future/naive times and replayed exports.
- Mutating claimed URL/time/status must never yield trusted-public authority,
  even if a forged export happens to pass content comparison.
- Existing tests still reject a HAR receipt as TRUSTED_PUBLIC_CAPTURE_REQUIRED;
  no filesystem/network/browser/database effects in the pure parser.

Current completion boundary: a pure synthetic-only parser is implemented in
`scripts/revenue_mvp_har_review.py`. Its strict minimal HAR subset is not a
supported Chrome/exporter profile: optional standard fields outside the subset
are rejected. Even matching content returns BLOCKED / HAR_PROVENANCE_UNCONFIRMED
because no exporter provenance profile is supported. No real HAR file has been
acquired/read, and no live-verification claim is made. No CLI or trusted-capture
bridge is provided. Tests cover synthetic inputs only; additional exporter-profile
and security acceptance tests remain required before any real-file use.

### Additional local review

The synthetic suite now covers envelope-level private fields, cookies and
authorization, case-insensitive header duplicates, nested/escaped duplicate
JSON keys, scanner quoting, depth/size boundaries, invalid Unicode/base64,
non-finite and oversized numbers, exact freshness boundaries, future completion,
timing inconsistencies, stale replay, CRLF comparison and unknown-hash suppression.
File opening, urllib transport and SQLite connection are guarded in unit tests.
These guards are representative effect checks, not a sandbox or a security proof.

Review found no need to relax the strict subset. Ordinary Chrome HAR exports
can contain currently unsupported standard fields; compatibility is deliberately
unproven. Accepted metadata and creator strings are claims, not authenticity.
Even repeated content matches remain BLOCKED. No real-data acceptance, transport
adapter or new publication authority is introduced by these additional tests.
