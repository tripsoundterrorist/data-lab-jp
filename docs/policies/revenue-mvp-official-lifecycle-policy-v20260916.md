# Revenue MVP Official Lifecycle Policy v2026-09-16

Status: isolated pure policy candidate. Publication and production Gates remain
closed.

This contract implements only the confirmed operational scope supplied on
2026-09-16:

- an item not returned by the API is excluded from affiliate candidacy and the
  public listed site;
- a visible item whose affiliate URL is absent or unknown is also excluded;
- an API rate-limit or error result stays excluded and requires a bounded wait,
  stop-on-rate-limit behavior, and at most one retry candidate;
- preorder or out-of-stock signals alone do not exclude an otherwise visible
  item with an observed affiliate URL.

The policy accepts only a sanitized observation, an affiliate-URL presence
boolean, and a fixed inventory signal. It never accepts or returns a URL,
content identifier, path, credential, provider payload, raw exception, rank,
offset, or schedule. The five-minute wait ceiling and single retry are local
safety maxima, not statements about the provider's update timing. No recurrence
frequency is defined.

`ELIGIBILITY_CANDIDATE` is not publication permission. The output always keeps
Publication Gate mutation false. Public rank numbers, offset-derived rank,
update-frequency claims, and internal history retention permission are also
always false because the official response did not resolve them.

The sanitized DMM Product Search API v3 reference reviewed on 2026-09-16
defines request `offset` and response `first_position` as the search start
position for pagination. This contract records both as
`PAGINATION_SEARCH_START_POSITION`; neither is a public rank or ordinal ranking
claim. The reference screenshot itself is not stored in Git.

This module performs no API call, database/filesystem operation, scheduler
change, external send, affiliate enablement, artifact publication, deployment,
route activation, or secret change. A later integration Gate must explicitly
review how a candidate is consumed without weakening the existing Publication
Gate.
