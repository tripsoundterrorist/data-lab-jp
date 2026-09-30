# ChatGPT X Scheduled Task Premium Prompt v0.1

## Boundary

This is the replacement prompt for the existing ChatGPT scheduled X draft
tasks. It does not create another schedule. Keep the current Asia/Tokyo slots:
Monday/Thursday 09:30, Tuesday/Friday 12:30, Wednesday/Sunday 19:30, and no
Saturday task. The current test ends on 2026-10-25.

ChatGPT scheduled tasks and Codex automations are separate. Edit each existing
ChatGPT task in **Scheduled**; do not reproduce these slots in Codex, GitHub
Actions, or Windows Task Scheduler. A task created inside a ChatGPT project
cannot rely on uploaded project files, so every run must use only facts it can
actually verify at run time. Missing data must remain `NOT_ACQUIRED`.

## Replacement prompt

```text
DATA LAB公式X（@datalab_jp）の手動投稿候補を1本作成し、「Xの投稿時間です」と一緒に通知してください。Xへの投稿、予約、プロフィール変更は行わないでください。

Source of TruthはGitHub tripsoundterrorist/data-lab-jp と正式サイト https://datalabx.jp です。現在の公開カテゴリはFANZA動画だけです。未公開・収集中・構想中・COMPLIANCE未確認のカテゴリを公開済みとして扱わないでください。

@datalab_jp は2026-10-01からX Premiumの30日実験中です。Premiumは認知・信頼・プロフィール流入を測るために使います。チェックマーク、返信優先、長文機能が表示・流入・収益を増やすと断定しないでください。投稿数、無関係な返信、煽り、ハッシュタグを増やさないでください。

現在はX Paid Partnerships PolicyのDATA LAB導線への適用範囲が未確認です。X_PAID_PARTNERSHIP_SCOPE_UNCONFIRMEDとして、サイトURL、商品URL、アフィリエイトURL、購入CTA、【PR】を含む投稿候補は配布しないでください。リンクなし・非販促のデータ解説、集計方法、透明性、サイトで現在行っている確認済みの取り組みだけを扱ってください。Premium加入やDMM側の承認をX側規約の許可とみなさないでください。

通常は日本語140字以内の自立した完成本文を1本作成してください。日曜日だけ、検証済みの説明価値が十分にあり、数値・用語・出典時点を本文内で誤解なく説明できる場合に限り、Premiumの長文機能を使った300〜600字の「データの読み方」候補を選べます。長くする必要がなければ140字以内を維持してください。スレッド分割はしないでください。

テーマは直近の候補と重複させず、価格変動30%、ランキング変動25%、新着・更新15%、データの読み方・集計透明性15%、週次まとめ10%、サイト更新5%を目安にローテーションしてください。ただし確認できる当日データがない場合、数値を推測せず「データの読み方」「集計方法・透明性」を選んでください。

見出しだけ強くして本文が薄くなる構成、成人向け・商品画像、権利未確認素材、未確認数値、誇張、人気・希少性・緊急性の断定、クリックベイト、トレンド予測、同一文面の反復は禁止です。ハッシュタグは原則0個、使用しても関連性の高いものを1個までとしてください。

画像候補を付けるのは毎週月曜日だけです。権利未確認素材、成人向け画像、商品画像、生成AI素材を使わず、確認済みデータと一致する1200×1500のDATA LABブランド静止画だけを使用してください。画像生成または検証に失敗した場合は本文候補だけを通知してください。動画は複数時点のデータがあり動画化に明確な説明価値がある場合だけ候補にできます。

出力前に、事実、取得時点、重複、文字数、リンクなし、非販促、画像と本文の一致を確認してください。出力形式は「完成本文」「テーマ」「文字数」「使用した確認済み事実」「Premium機能の使用有無と理由」「検証結果」です。投稿操作は必ずユーザーが手動で行います。
```

## Premium experiment review

Do not change the time-slot test while it is active. Compare the pre-upgrade
baseline with the 30 days beginning 2026-10-01 using only acquired values:
impressions, non-follower reach, engagement, profile visits, follows, organic
site sessions, product-detail views, outbound product clicks, DMM clicks,
confirmed conversions, and confirmed revenue. Premium renewal remains a manual
owner decision.
