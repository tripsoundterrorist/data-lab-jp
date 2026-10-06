# Doujin compliance follow-up packet v0.1

`scripts/doujin_compliance_followup_packet.py` produces a minimal Japanese
follow-up draft containing only the five questions that cannot be covered by
the current prior-evidence scope review or DATA LAB internal policy.

The packet excludes the seven prior-evidence candidates and the two internal
COMPLIANCE questions. It includes no URL, product identity, account detail,
credential, or raw prior response. The operator must compare the rendered draft
with the current official guidance and approve the exact message before any
external submission.

As of 2026-10-06 JST, the packet remains unsent until the official response to
the already-submitted BOOKS follow-up (the remaining ebook-comic question and
FANZA ebook BL questions) has been received and reviewed. The operator must then
remove overlapping or unnecessary questions before deciding whether to send
this separate doujin inquiry.

`READY_FOR_MANUAL_SEND_REVIEW` is not send authorization. The packet always
keeps `send_authorized`, `external_send_performed`, and `publication_allowed`
false. Sending, response intake, COMPLIANCE decision, Gate review, and any
publication remain separate actions.
