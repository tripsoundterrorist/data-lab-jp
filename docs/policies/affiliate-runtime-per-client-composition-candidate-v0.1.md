# DATA LAB Affiliate Runtime Per-Client Composition Candidate v0.1

This non-deployed composition orders the existing route guard, per-client
rate-limit adapter, read-only eligible D1 lookup, and guarded pipeline callback.

An invalid route is rejected before the rate-limit binding. A missing or
malformed opaque client key is rejected before the binding and D1. A rejected
or malformed binding result is rejected before D1. The pipeline callback is
reachable only after rate-limit approval and exactly one eligible D1 row.

The opaque key is an explicit trusted-boundary input. This composition does not
derive it from an IP address, Request, header, cookie, query parameter, or
browser value. It does not implement or infer the key issuer or lifecycle.

This file remains outside `functions/` and adds no binding/configuration,
handler, redirect response, log, deployment, D1 write, eligibility change,
secret, paid resource, or affiliate-state change. Deployment preflight remains
fail closed until the external key issuer, numeric limit, binding, privacy, and
production runtime evidence are separately reviewed.
