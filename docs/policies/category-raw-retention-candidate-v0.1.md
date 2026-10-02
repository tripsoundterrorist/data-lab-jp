# Category raw retention candidate v0.1

Date: 2026-10-02

Status: unresolved policy candidate; collection-only

## Current implementation facts

The isolated category database stores a sanitized item-shaped JSON observation
in `category_item_snapshots.sanitized_raw_json`. The collector recursively
removes keys whose normalized names indicate affiliate URLs or IDs, API IDs,
authorization, credentials, passwords, secrets, or tokens. The current health
Gate also scans stored JSON keys and fails closed when such a key is present.

The sanitized observation can still contain product metadata, URLs, image
facts, campaign structures, and other source fields. Secret-key removal does
not establish a right to retain, transform, or publish those fields.

## Candidate handling boundary

- Keep the category database private and outside public artifacts.
- Do not copy raw observations into D1, static output, logs, analytics, SNS,
  evidence receipts, or Git.
- Do not expose item-level raw data through health or value-audit output.
- Keep access limited to the local collector, backup, health, and explicitly
  reviewed local audit paths.
- Do not enable automatic deletion, compaction, migration, or indefinite
  retention policy changes without a reviewed recovery and compliance plan.
- Do not expand the stored raw field set until field-level review is complete.

## Unresolved decisions

The following remain `UNCONFIRMED` and must be resolved from current official
terms or a category-specific official response:

- whether sanitized item responses may be retained historically;
- the permitted retention duration;
- whether removal is required after a product disappears or becomes ineligible;
- whether campaign, review, sample-image, URL, and image structures may be
  retained and transformed;
- backup retention and deletion obligations;
- whether normalized historical price facts may outlive the raw observation.

Until these are resolved, this document does not authorize a new retention
duration, a new backup destination, public use, or additional raw collection.
Existing collection remains isolated and publication-closed; any change to its
scope, frequency, retention, or deletion behavior requires a separate review.
