# Product image public health v0.1

`scripts/product_image_public_health.py` performs a read-only aggregate check of
the images rendered on the live 100-product Revenue MVP surface.

It requires exactly 100 unique HTTPS image URLs on the official
`pics.dmm.co.jp` host, sends bounded HEAD requests with at most five concurrent
workers, and accepts only HTTP 200 or 206 responses whose content type starts
with `image/`. Output contains aggregate counts and reason codes only; it never
contains product identifiers, titles, image URLs, credentials, or response
bodies.

Any missing, duplicate, wrong-host, credential-bearing, query-bearing,
non-image, non-success, network, decoding, or parsing result returns
`FAILED_SAFE`. The check performs no remote write, repair, retry, publication,
schedule change, notification, or image replacement. A passing result confirms
availability only at the observation time and does not grant new media rights.

This check is manual in v0.1. Connecting it to a schedule or notification path
requires a separate reviewed Gate so the existing daily affiliate task and API
budget remain unchanged.
