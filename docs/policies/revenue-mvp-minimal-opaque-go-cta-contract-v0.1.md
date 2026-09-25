# Revenue MVP Minimal Opaque `/go/` CTA Contract v0.1

This is a separate implementation-review scope. It does not modify or expand
the previously approved CTA-free exact unordered surface.

The only candidate public route is `/go/{opaque_public_id}`, where the ID must
match the existing `itm_` namespace. The provider affiliate URL remains in a
server-side private lookup and must never enter Public JSON or HTML. The CTA
must display the proximate disclosure `【PR】FANZAで確認`. Server-side lookup and
rate limiting are mandatory.

When more than one reviewed item is available, an offline canary packet may
select exactly one item by the lexicographically smallest derived opaque ID.
This deterministic selection has no ranking, popularity, recommendation, or
quality meaning. Every source candidate must first bind uniquely to immutable
saved evidence; ambiguity blocks the whole packet.

Passing this pure contract grants only implementation review. Publication,
affiliate eligibility, Gate mutation, deployment, production activation, and
another API request all remain forbidden until separately reviewed and
explicitly approved.
