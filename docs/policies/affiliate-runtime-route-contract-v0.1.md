# DATA LAB Affiliate Runtime Route Contract v0.1

## Scope

This pure contract validates sanitized HTTP request facts for a future
server-side affiliate route. It has no web handler, platform adapter, secret
binding, database access, API request, redirect emitter, logging, or deployment.

## Request boundary

- exact route: `/go/itm_<24 lowercase hexadecimal characters>`;
- methods: uppercase `GET` and `HEAD` only;
- request bodies are forbidden;
- query strings, fragments, encoded path components, traversal, duplicate
  slashes, and malformed identifiers are rejected;
- guard inputs must be actual booleans.

## Activation order

The rate-limit decision is checked before publication/runtime activation facts.
The route becomes only a pipeline-invocation candidate when the official-answer
candidate, Publication Gate, runtime chain, rate limit, and proximate PR
disclosure are all explicitly true.

Closed activation guards return a generic 404 boundary so the route contract
does not disclose whether an item exists. A rejected rate-limit decision returns
429, a request body returns 400, and a forbidden method returns 405.

## Response boundary

Every result is bodyless, contains no redirect location, identifier, request
path, URL, or secret, and specifies fixed `no-store`, `no-cache`,
`no-referrer`, and `noindex` response metadata. A fully eligible request is a
302 candidate only; the contract cannot create or deliver a redirect.

## Activation boundary

Cloudflare-specific code, binding configuration, deployment, and production
activation require later review. Issue #66 and all public-data and production
gates remain unchanged and fail-closed.
