# Affiliate Pages Entrypoint Candidate v0.1

This non-deployed candidate composes the reviewed route guard, privacy-preserving
client-key derivation, per-client Rate Limiting adapter, eligible-only D1 lookup,
and Workers DMM provider into one Pages-compatible request handler.

It is stored under `runtime-candidates/`, does not export `onRequest`, and no
repository `functions/` directory exists. It therefore cannot become a Pages
Function through the current repository layout.

Only a fully eligible request can return a 302 response. All responses disable
caching, referrer forwarding, and indexing. Invalid methods, paths, query
strings, release facts, bindings, client addresses, D1 state, rate-limit results,
upstream responses, or downstream delivery fail closed without reflecting
identifiers, URLs, credentials, headers, bodies, or exceptions.

This candidate does not configure the Rate Limiting binding or client-key
secret, connect the CTA disclosure, create a deployment wrapper, deploy, publish,
enable D1 rows, activate affiliate behavior, or change billing.
