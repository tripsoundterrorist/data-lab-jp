# DATA LAB Affiliate Link Adapter v0.1

## Responsibility and retention boundary

The adapter temporarily accepts a link value, performs strict URL validation, passes sanitized facts only to Affiliate Link Policy v0.1, and returns a bounded UI-safe summary. It does not reproduce policy decisions. The URL value is memory-only and is never placed in a database, Public JSON, artifact, log, exception, test output, or safe result. Tests use only reserved dummy domains such as `example.invalid`; no real affiliate or DMM URL is used.

## URL validation

HTTP and HTTPS are accepted to match the existing artifact URL contract. javascript, data, file, FTP and other schemes are rejected, as are localhost, loopback IPv4/IPv6, UNC and Windows paths, embedded user information, malformed or hostless URLs, invalid ports, controls, CR/LF, and whitespace injection. Validation does not establish availability, affiliate eligibility, or purchasability.

## UI, Gate, and lifecycle boundary

After URL validation, Rights, context, lifecycle, verification, Gate, and PR facts are delegated to Affiliate Link Policy. URL validity alone cannot render a link. PR disclosure remains mandatory. `production_render_allowed` can be true only if the delegated policy allows it and Publication Gate `overall_eligible` is true. The adapter never changes the Gate, lifecycle, publication status, UI, or blocker state and v0.1 performs no real UI handoff.

The safe result contains only adapter version, validation status, link status, UI candidate, production-render permission, PR requirement, and deterministic reason codes. Unknown versions, extra fields, and internal exceptions fail closed without echoing input.
