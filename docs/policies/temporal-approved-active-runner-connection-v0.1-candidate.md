# Temporal Approved Active Runner Connection v0.1 Candidate

This candidate connects the validated four-population temporal bundle to the
existing isolated active-runner boundary only after an exact, scope-bound
approval object and the current connection review both validate.

The only accepted persistence target is an `IsolatedTemporalStateStore`
constructed through its test factory. A missing, false, wrong-version, or
wrong-scope approval stops before filesystem access. Changed review evidence,
an invalid store, an invalid bundle, or a downstream failure also stops closed.
Uncertain persistence requires recovery and is never retried automatically.

A successful result means only that the approved in-process connection assessed
and stored four states in a caller-owned temporary test directory. It grants no
API request, scheduler change, production write, deploy, publication, affiliate
activation, route, D1, or billing authority. Connecting this adapter to a live
collector or scheduler requires another separately reviewed Gate.
