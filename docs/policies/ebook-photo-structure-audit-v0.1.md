# FANZA ebook photo structure audit v0.1

Updated: 2026-10-03 JST

## Purpose

This audit reads the collection-only `ebook_photo` dataset and reports whether
its observed structure is suitable for later, non-public technical preparation.
It does not authorize publication, affiliate use, image use, sitemap changes,
or Production work.

## Source boundary

The exact source namespace is fixed to:

- site: `FANZA`
- service: `ebook`
- floor: `photo`
- content type: `ebook_photo`

This category is not treated as equivalent to
`DMM.com / ebook / photo / photo_book`, even where field shapes or product URL
hosts overlap.

## Aggregate checks

- item and latest-snapshot counts
- exact source-namespace count
- title, release date, HTTPS product URL, and HTTPS image coverage
- series and genre coverage
- current price, list price, discount, and complete review-pair coverage
- per-source contributor-role item and entry counts
- malformed JSON and malformed entity counts

The audit does not output product IDs, titles, URLs, image URLs, prices, review
values, or entity IDs and names.

## Entity boundary

Observed `actress`, `author`, and `manufacture` values are retained only as
source role labels. This audit does not translate them into performer, creator,
publisher, maker, or brand semantics and does not merge them with entities from
video or other photo-book namespaces.

## Safety boundary

The maximum result is `READY_FOR_EBOOK_PHOTO_STRUCTURE_REVIEW`. All downstream
permissions remain false:

- entity semantics and field rights
- Compliance approval
- database or artifact writes
- publication, affiliate, sitemap, and Production changes

Official scope confirmation, 03 COMPLIANCE review, and explicit user approval
remain necessary before any public use.
