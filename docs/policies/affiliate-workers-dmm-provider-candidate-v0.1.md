# Affiliate Workers DMM Provider Candidate v0.1

`runtime-candidates/affiliate-workers-dmm-provider.mjs` is a non-deployed
server-side provider candidate for the Cloudflare affiliate route.

It makes one bounded HTTPS ItemList request for the already D1-resolved FANZA
video content ID, requires an exact response match, validates the API-issued
affiliate URL against approved DMM/FANZA HTTPS host boundaries, and passes that
URL only to a trusted in-process callback. The safe result contains no URL,
content ID, credential, upstream body, HTTP detail, or exception text.

The response is limited to 1 MiB, redirects are rejected, and the request times
out after 15 seconds. Missing secrets, malformed identifiers, ambiguous or
invalid responses, unsafe URLs, network failures, and delivery failures all fail
closed. Nothing is logged or persisted.

This candidate does not create a Pages Function, route, secret, Rate Limiting
binding, redirect response, deployment, publication, or affiliate activation.
