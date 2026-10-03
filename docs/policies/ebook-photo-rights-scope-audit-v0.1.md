# FANZA ebook photo field-rights scope audit v0.1

Updated: 2026-10-03 JST

## Purpose

This audit separates fields that may be reviewed for reuse under the existing
Rights Decision Matrix from fields that require exact source-scope confirmation
or remain prohibited. It does not extend a prior answer to
`FANZA / ebook / photo / ebook_photo` and does not authorize publication.

## Review candidates only

- title and product page URL
- series and genre
- current price
- review count and average
- product main image

An existing `APPROVED` matrix entry is only evidence that the field can be
reviewed. It is not proof that the answer covers this exact floor, category, or
image context.

## Exact-scope review required

- public ID, release date, optional list price
- observation time and freshness state
- `actress`, `author`, and `manufacture` source-role semantics
- exact applicability of earlier display and retention answers
- product-image conditions for this exact FANZA ebook photo scope

Role labels are not translated into performer, creator, publisher, maker, or
brand meanings and are not merged with video or DMM photo-book entities.

## Prohibited fields

- product description
- user review text
- raw API response

These fields remain excluded regardless of structural availability.

## Safety boundary

The maximum result is `READY_FOR_EBOOK_PHOTO_COMPLIANCE_SCOPE_REVIEW`.
Exact-scope confirmation, contributor semantics, image scope, field rights,
publication, affiliate activation, Production, and Publication Gate changes all
remain unapproved. A policy mismatch makes the audit fail closed.
