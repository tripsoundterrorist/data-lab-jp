# DATA LAB Affiliate Item Lookup Private Export v0.1

## Scope

The exporter prepares a local SQL import candidate from the existing SQLite
`items` table. It does not connect to Cloudflare, create D1, import data, call
DMM, deploy a handler, or enable an affiliate row.

## Source boundary

- SQLite is opened with `mode=ro` and `query_only`;
- only `site`, `service`, `floor`, and `content_id` are read;
- the supported scope is exactly FANZA / digital / videoa;
- malformed, duplicate, unsupported, or empty input fails closed;
- source bytes remain unchanged.

## Output boundary

Output must be a new `.sql` file directly under an explicitly supplied private
root. The intended repository location is `runtime/private/`, which is ignored
by Git. Existing targets are never overwritten. Writes use a same-directory
temporary file, fsync, restricted permissions where supported, and atomic
replacement.

Every generated row uses schema defaults: pending rights, pending lifecycle,
pending verification, and `affiliate_enabled=0`. Therefore imported rows remain
absent from the eligible runtime view.

The safe result contains only row count, booleans, a SHA-256 digest, and bounded
reason codes. It contains no paths, public IDs, content IDs, SQL, URLs, or
credentials.

## Activation boundary

Running against the real database, inspecting or transferring the private SQL,
creating/importing D1, configuring bindings, changing eligibility, or deploying
the runtime requires separate review and approval. Issue #66 and every
publication and production gate remain fail-closed.
