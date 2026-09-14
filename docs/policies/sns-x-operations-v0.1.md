# SNS X Operations v0.1

## Scope and current state

This policy governs the X account `@datalab_jp` as a high-quality acquisition
channel for `https://datalabx.jp`. GitHub and sanitized COMPLIANCE decisions are
the source of truth. The currently verified public category is **FANZA動画**.
Ideas, Issues, collection-only work, unpublished code, and unverified categories
must not be described as available.

The account-registration condition `SNS_ACCOUNT_REGISTRATION` is verified.
`SNS_TO_SITE_TO_FANZA_FUNNEL`, `SNS_PRODUCT_MEDIA_USE`, and
`AUTOMATED_FACT_POSTING` remain unverified. Therefore X remains `PREVIEW_ONLY`.
Registration approval alone does not authorize posting, media, affiliate routes,
automation, or any Publication Gate change. The separate Lifecycle / Sort answer
also remains pending and does not open the Web Revenue MVP Publication Gate.

## Current X presentation

- Header primary: `FANZA動画の価格・人気・ランキングをデータで分析`
- Header secondary: `価格推移・値下がり・ランキング変動をわかりやすく可視化`
- Do not use `トレンド予測` or any claim whose implementation and calculation
  basis cannot be verified.
- A pinned post that explains an affiliate path must retain `PRを含みます`.

These are approved proposals for manual presentation work, not authority for an
automatic X update.

## External six-week notification test

ChatGPT-side notifications are configured from 2026-09-15 through 2026-10-25:

| Day | JST |
| --- | --- |
| Monday / Thursday | 09:30 |
| Tuesday / Friday | 12:30 |
| Wednesday / Sunday | 19:30 |
| Saturday | no post |

Each notification contains `Xの投稿時間です` and one completed draft for review
and copy. This is an external configuration only. Do not duplicate it in this
repository, GitHub Actions, Windows Task Scheduler, or another automation.

The former daily 19:00 draft generation and daily 07:00 draft notification are
retired configurations. The repository currently contains no matching SNS
schedule. If either is discovered externally, first inspect ownership and impact,
then propose disablement or migration; do not delete it automatically.

## Draft rules and rotation

Generate one Japanese draft per notification, no more than 140 Japanese
characters, based only on verified facts. Prefer one observable change from that
day over strong promotion of a single product. Avoid repetition across prior
posts and notification drafts. Use no hashtag by default and at most one directly
relevant hashtag. Never use adult/explicit images, unverified product media,
unsupported claims, urgency, scarcity, misleading popularity, clickbait, or
unrelated links. CTA wording must be COMPLIANCE-verified.

Any post containing an advertising or affiliate path must state `【PR】` clearly
in the post body. This rule does not grant permission to use such a path while
the SNS funnel condition remains unverified.

Rotate themes across time slots without associating a theme with a supposedly
better time. Preserve this target mix where applicable:

- Price change: 30%
- Ranking change: 25%
- New / updated data: 15%
- How to read the data and aggregation transparency: 15%
- Weekly summary: 10%
- Site update: 5%

## Measurement

Record, where X makes the metric available: impressions, non-follower reach,
engagement, profile visits, follows, link clicks, CTR, theme, posting date/time
and slot, and whether a PR link was present. Compare time slots while controlling
for weekday, theme, and link presence. Do not attribute performance to time alone
or select a winner from impressions alone.

## Category expansion

Only when GitHub shows a category is actually public and COMPLIANCE confirms it
may be promoted, prepare update proposals for the profile, header, pinned post,
category announcement, normal-post templates, and required PR / affiliate
disclosures. Proposals are notification-only: never update X or GitHub
automatically. Collection start, an Issue, a plan, or unpublished implementation
does not satisfy the trigger.

## Future automatic posting boundary

Keep these independently stoppable stages: data acquisition; draft generation;
fact verification; duplication and quality checks; COMPLIANCE check; user
approval; posting; result retrieval; analysis; improvement.

The design must fail closed and preserve human approval before posting, a final
publication check, deduplication, idempotency, audit records linking post ID,
source data, generated text, and approval result, safe API-failure shutdown,
duplicate-send prevention, bounded retry, emergency stop, and rollback. It must
not modify credentials or `.env`, expose secrets in logs/commits/notifications,
auto-repair, auto-unlock, or activate LIVE before official rules, API terms, and
fees are verified. Current operation performs no X post, external send, schedule
registration, media use, affiliate activation, or LIVE transition.

Ownership remains split: content and SNS strategy in 04 SNS; automation runtime
in 05 OPS; revenue value in 02 REVENUE; publication permission in 03 COMPLIANCE;
and site implementation in 01 DEV.
