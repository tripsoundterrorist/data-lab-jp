# Affiliate D1 import hardening v0.2

## Objective

Harden the private affiliate lookup validation path immediately before any manual Cloudflare D1 creation/import step.

## Changes

- Reject direct candidate/schema symlink inputs before path resolution.
- Read each filesystem input into one stable byte snapshot.
- Verify file identity metadata before and after snapshot reads and fail closed if the file changes while being read.
- Compute SHA-256 from the exact snapshots that are subsequently validated.
- Run the in-memory SQL validation from those same snapshots instead of reopening the candidate/schema after hashing.
- Keep `d1_import_allowed=false` and `cloudflare_write_performed=false`; this hardening does not authorize or perform any Cloudflare write.

## Failure behavior

The path fails closed for symlink inputs, unavailable inputs, unstable snapshots, hash mismatches, invalid SQL shape, enabled affiliate rows, non-pending defaults, or non-empty runtime eligibility.

## Scope

This gate only strengthens local pre-import evidence. It does not resolve DMM/FANZA rights, lifecycle, publication, or SNS policy questions and does not unlock the Revenue MVP publication gate.
