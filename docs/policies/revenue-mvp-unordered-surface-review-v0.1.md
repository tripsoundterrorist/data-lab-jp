# Revenue MVP unordered reduced-surface review contract v0.1

Status: review-only contract. This document does not grant production publication, affiliate eligibility, CTA display, external distribution, or any Gate mutation.

## Purpose and evidence boundary

This is a narrow manual-Gate review candidate for an unordered reduced surface. It is based on the confirmed lifecycle interpretation recorded in [revenue-mvp-official-lifecycle-policy-v20260916.md](revenue-mvp-official-lifecycle-policy-v20260916.md) and the official-response review record dated 2026-09-16.

The contract deliberately does not rely on unresolved formal questions about API offset or position as a public representation, source-result ordering, update or requery behaviour, or historical retention. It is therefore not evidence that those matters are permitted.

## Candidate prerequisites

All conditions below are required. Any missing, stale, malformed, or contradictory condition is BLOCKED.

- The sanitized official lifecycle decision is the current ELIGIBILITY_CANDIDATE; it still has every publication, rank or offset, update-frequency, and internal-history permission set to false.
- The lifecycle freshness confirmation is true.
- The displayed API取得確認時刻 is timezone-aware and exactly equals the lifecycle observation timestamp.
- The title has confirmed provenance from the same immutable source snapshot. A current mutable item row alone is insufficient.
- If price is displayed, both current_price and price_observed_at are present, and the price timestamp exactly equals API取得確認時刻.
- The presentation mode is exactly UNORDERED_GRID; sorting controls, position indicators, history, and affiliate CTA are all absent.

## Allowed display contract

Only these field names may be considered by a future, separately reviewed renderer:

- title
- api_observed_at (required; label: API取得確認時刻)
- transparency_notice (required; exact text below)
- current_price and price_observed_at together, only when their shared observation binding is confirmed

The required transparency notice is:

> 表示内容は、各項目を確認できた時点の記録です。順位・並び順・更新頻度・在庫・販売状況を示すものではありません。

Allowed claim codes are only API_OBSERVED_AT, UNORDERED_PRESENTATION, and, when price is displayed, PRICE_OBSERVED_AT.

## Explicitly forbidden

The renderer must not accept or derive ordinal or position or rank, offsets, source order or sort labels, review order or scores, update frequency or latest or realtime wording, availability or inventory or sale-stop claims, any history or price history, content identifiers, affiliate URLs, affiliate disclosures, or affiliate CTA.

This contract also forbids sort controls, position indicators, API-order labels, and any production activation. Unordered means the rendered collection must not make or imply an ordering assertion; a future layout implementation requires its own manual review for that property.

## Expiry and remaining blockers

This candidate expires immediately if freshness is no longer confirmed, the lifecycle decision changes, the title or price snapshot binding cannot be proven, the observation timestamps differ, the required notice changes, or any forbidden field, claim, or control is introduced. Re-evaluation creates another review candidate only; it never promotes publication.

Before any external or production use, all of the following remain BLOCKED:

1. Manual Publication Gate review and an explicit PASS under the then-current policy.
2. A separately reviewed renderer that proves the required fields and provenance and unordered presentation without adding a route, CTA, or distribution.
3. Confirmation of any additional display semantics if the scope expands beyond this exact contract.

No new official inquiry is needed for this bounded manual-review artifact because it makes no claim about the unresolved semantics. An official inquiry is required before proposing any ranking, ordering, update, history, availability, or CTA behaviour.
