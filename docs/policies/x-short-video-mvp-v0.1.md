# X Short Video Generation MVP v0.1

This is a local, non-posting candidate for `@datalab_jp`. It uses Python,
Pillow, a Japanese system font, and an operator-supplied FFmpeg/ffprobe binary.
FFmpeg was selected over Remotion because the single deterministic template
does not justify Node, Chromium, or a rendering framework. No paid video AI,
paid media, X API, monthly service, product image, audio, narration, or BGM is
used.

One exact structured input drives both the Japanese post text and a 10-second,
1080x1920, 30fps, silent H.264 MP4. The three scenes are theme/headline,
verified short explanation, and the DATA LAB/datalabx.jp end card. Safe margins,
bounded Japanese text, codec, dimensions, duration, frame rate, audio absence,
and file size are validated before delivery readiness.

The input Gate requires a source ID and checked time, `VERIFIED_CURRENT`
freshness, the configured JST slot, no Saturday run, at most 140 post
characters, matching numeric claims, required `【PR】`, `sensitive_media=false`,
and the fixed template. Unknown or malformed facts fail closed. No product data
or media is inferred.

The external ChatGPT notification schedule remains the only schedule. The
repository config documents the 2026-09-15 through 2026-10-25 test but cannot
register a task. It must not modify the existing notifications. A caller may run
the CLI shortly before an existing notification and attach the returned local
MP4 plus `post_text`; integration is not automatic in v0.1.

Generation state is stored only under ignored `runtime/private/x-video-mvp`.
The ledger hashes `content_id`, prevents reuse and duplicate delivery, and never
posts or notifies. If video rendering or probing fails after input validation,
the result is `TEXT_READY_VIDEO_FAILED`: the verified post text remains ready,
no incomplete MP4 is returned, and the reason is a bounded code. Posting,
upload, X API use, schedule creation, affiliate activation, Publication Gate
changes, and LIVE operation remain unavailable.

Local usage after installing a free FFmpeg build outside the repository:

```text
python scripts/x_short_video_mvp.py --input tests/fixtures/x-short-video-safe-v0.1.json
```

The notification owner must inspect `text_status`, `video_status`, and
`duplicate_notification_blocked`. Only `video_status=READY` may expose the MP4;
text delivery may continue when video status is `FAILED`. Actual notification
attachment integration belongs to 05 OPS and requires a separate review of the
ChatGPT automation boundary.
