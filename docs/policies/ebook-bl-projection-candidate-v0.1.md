# BL ebook non-public projection candidate v0.1

Updated: 2026-10-03 JST

## Purpose

This document defines a structure-only candidate for a future projection of
`FANZA / ebook / bl / ebook_bl`. It does not approve field rights, entity
semantics, affiliate activation, publication, sitemap changes, or Production
writes.

## Evidence boundary

The current collection audit found 107 BL ebook items. All observed product
URLs used the `book.dmm.co.jp` host. The observed source labels were `author`
and `manufacture`; these labels are retained without translating them into
creator, publisher, maker, or brand semantics.

The associated Compliance questionnaire remains deferred until the current
official inquiry has been answered and duplicate questions have been removed.

## Exact namespace and identity

- site: `FANZA`
- service: `ebook`
- floor: `bl`
- content type: `ebook_bl`
- public ID candidate: `ebl_` followed by 24 lowercase hexadecimal characters
- product URL host: `book.dmm.co.jp`

No other ebook floor or public category inherits this namespace.

## Candidate allowlist

- title and raw release date
- current price and optional list price
- separate `author` and `manufacture` reference arrays
- series and genre reference arrays
- source product URL
- review average and count, either both present or both unavailable
- timezone-aware observation timestamp and freshness state

## Explicit exclusions

The allowlist excludes product images, descriptions, review text, raw API
responses, affiliate URLs and parameters, request/query context, and unknown
fields. Adding any excluded or unknown field makes validation fail closed.

Product images are excluded even though image URLs were observed in collection.
Their use conditions have not been confirmed for this exact BL ebook scope.

## Safety boundary

A structurally valid candidate stops at
`READY_FOR_FIELD_AND_SEMANTICS_REVIEW`. Every approval or activation flag stays
false:

- contributor semantics confirmed
- field rights confirmed
- Compliance approved
- publication allowed
- affiliate activation allowed
- sitemap change allowed
- Production write allowed

The validator has no API, database-write, file-write, Publication Gate, or
runtime publication connection. No real-data projection artifact is generated.
