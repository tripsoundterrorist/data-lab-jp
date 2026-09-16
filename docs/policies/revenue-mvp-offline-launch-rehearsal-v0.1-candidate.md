# Revenue MVP Offline Launch Rehearsal v0.1 Candidate

Status: synthetic, in-memory rehearsal only. Launch remains prohibited.

The rehearsal exercises the merged lifecycle-to-artifact integration using one
safe synthetic `local_validation_only` artifact and fixed evidence. It verifies:

- one allowed candidate remains paired in index and detail while CTA stays false;
- non-target, missing affiliate URL, API error, rate limit, and stale scenarios
  disappear from index and detail together;
- manifest item count and artifact digests are regenerated and validated;
- position, offset, rank, top, latest, and other invalid public fields or claims
  fail closed before any filtered output is accepted;
- a validated immutable snapshot restores the original local artifact
  byte-for-byte and produces the same SHA-256 on repeated restoration; and
- every smoke result keeps production publication and Gate mutation false.

Rollback is an in-memory copy from caller-supplied original bytes. It does not
read, write, rename, delete, deploy, or replace filesystem content. The harness
performs no real API or D1 call, route or scheduler change, external send,
secret operation, Publication Gate change, production write, or launch.
