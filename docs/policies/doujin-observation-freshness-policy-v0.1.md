# Doujin observation freshness policy candidate v0.1

Status: internal candidate only; not connected to publication

Future doujin pages may describe a verified timestamp only as
`DATA LAB確認日時`. They must not call it the provider's update time, latest
official update, real-time data, or a provider refresh schedule.

The candidate reuses the isolated category collector's existing 26-hour health
boundary. An observation at or below that age may become a display candidate;
an older observation is `STALE` and is excluded. A future timestamp, naive
timestamp, malformed timestamp, or clock reversal fails closed. Reusing this
boundary avoids introducing a second freshness definition during preparation;
changing it requires a separate reviewed policy.

`scripts/doujin_observation_freshness_policy.py` is pure and performs no API,
database, filesystem, artifact, sitemap, affiliate, or Production operation.
Even `CURRENT` sets only `display_candidate=true`; publication and Gate changes
always remain false until all category Gates and explicit approval are complete.
