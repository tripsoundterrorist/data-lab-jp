# BL ebook projection readiness audit v0.1

Updated: 2026-10-03 JST

## Purpose

This audit applies the non-public BL ebook projection validator to every latest
collected `ebook_bl` snapshot. It outputs aggregate ready and blocked counts
only. It does not output product IDs, titles, URLs, prices, reviews, or entity
values, and it creates no projection artifact.

## Input boundary

The category collection health gate must be `HEALTHY`. The database is then
opened in SQLite read-only mode. The source namespace is fixed to
`FANZA / ebook / bl / ebook_bl`.

The existing BL rights-scope review and unsent Compliance questionnaire must
both be structurally ready. Their readiness is preparation evidence only. If
either contains an approval, send authorization, publication permission, or
other unexpectedly open gate, this audit fails closed.

## Projection boundary

Each latest snapshot is transformed in memory into the exact allowlisted
structure. Product images are not read into or included in the candidate.
`author` and `manufacture` remain separate source-labelled reference arrays;
the audit does not reinterpret their semantics.

For blocked rows, only fixed reason-code counts are reported. A partial review
pair is reported as `PROJECTION_REVIEW_PAIR_INCOMPLETE` without filling in a
missing value.

## Safety boundary

An aggregate structural result may reach
`READY_FOR_FIELD_AND_SEMANTICS_REVIEW`, but every downstream gate remains
closed:

- no artifact creation or database write
- no contributor or image semantics confirmation
- no field-rights or Compliance approval
- no publication, affiliate, sitemap, or Production permission

Official answers, 03 COMPLIANCE review, and explicit user approval remain
required before any public projection or runtime connection.
