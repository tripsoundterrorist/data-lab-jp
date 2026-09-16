# X static card MVP v0.1

Local candidate only. `scripts/x_static_card_mvp.py` reuses the video input
validator and generates a deterministic 1200x1500 PNG with Japanese text,
headline, explanation, required PR marker, DATA LAB and datalabx.jp. No product
image, AI image service, audio, invented chart, network, upload, notification,
posting, or scheduler is implemented. A valid input keeps text READY if image
generation fails. Output is private and excluded from Git.

Candidates are exclusively created directly in the approved output directory
and inherit its normal ACL. A completed, validated candidate is atomically linked
without overwrite; the staging file is removed on success or failure. No chmod,
ACL reset, or permission broadening is performed. Previously generated artifacts
with restricted temporary-directory ACLs are not repaired automatically; use a
fresh approved output directory for the delivery verification.

Usage: `python scripts/x_static_card_mvp.py --input INPUT.json`.
The scheduled_at field is the intended posting slot (for example Monday 09:30),
not the Monday 08:30 preparation time. The configured test dates still apply;
after the test ends, an owner-reviewed configuration update is required.

The existing Codex weekly review has a media-preparation instruction, not a
verified end-to-end delivery guarantee. Drive upload, private sharing inspection,
post-history deduplication and completion notification must be checked by the
caller. This renderer never marks a candidate as posted or notified. The separate
ChatGPT mobile reminder has not been confirmed as an active Scheduled Task.
An 08:35 reminder cannot claim an 08:30 run completed solely from elapsed time.

Preview must be visually checked before manual X posting. Compliance and current
publication conditions remain unchanged. No new schedule or production change.
