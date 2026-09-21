# Revenue MVP unordered review packet v0.1

`revenue_mvp_unordered_review_packet.py` builds a local manual-review packet
only from the latest snapshot when immutable title, lifecycle observation, and
snapshot timestamps are identical. Price is included only from that same
snapshot. Evidence older than 24 hours is excluded.

The packet contains only title, API observation time, the exact approved
transparency notice, and optional current price with its equal observation
time. It contains no item/content identifier, URL, affiliate value, source
sort, position, rank, history, availability, or update claim. List order is a
serialization detail and grants no order semantics.

The default run is read-only and writes nothing. Explicit output must be
outside the repository and is replaced atomically. Publication, production
activation, affiliate eligibility, Gate mutation, and CTA remain false. The
packet is not a public artifact and cannot activate a route or deployment.
