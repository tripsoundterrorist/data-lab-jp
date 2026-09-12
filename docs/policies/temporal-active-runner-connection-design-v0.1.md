# Temporal Active Runner Connection Design v0.1

Status: design ready for implementation review; no implementation or connection
is authorized.

The legacy runner has no explicit series identity and the legacy adapter enters
its write path with `dry_run=False`. It must not be reused or partially replaced.
A future boundary must accept one already-validated four-population bundle,
retain explicit series identity, use the isolated series runner, and expose only
an injected test-only persistence capability during its first implementation.

The design requires atomic rejection before the first write when bundle identity
is invalid, no legacy fallback, no network or scheduler capability, bounded safe
results, and a separate implementation approval.

This Gate uses source/signature inspection only. It invokes no runner or adapter,
performs no API request, filesystem or D1 write, migration, baseline activation,
scheduler change, deployment, publication, or affiliate operation. The next Gate
is explicit review of whether to implement the isolated connection boundary.
