# Revenue MVP Launch Rehearsal v0.1

This offline rehearsal verifies that the intended post-response launch path is
technically reachable without touching production. It uses only a future all-PASS
Gate fixture, an in-memory SQLite database with a synthetic row, the existing
mocked Worker entrypoint harness, and the fixed activation/rollback order.

The five required checks are: future Publication Activation eligibility under
explicit approval; one exact D1 eligible row; rollback to zero eligible rows;
the Worker redirect candidate harness; and response-first activation plus
Worker-first rollback ordering.

No real item identifier, API credential, affiliate URL, production database,
network request, deployment, publication, Cloudflare resource, plan, or billing
state is used or changed. Passing the rehearsal does not unlock any current Gate.
The real launch still requires the official DMM response, fresh evidence, and
separate production approval.
