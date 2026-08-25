# DATA LAB Rights Decision Matrix v0.1

- `policy_version`: `0.1`
- 根拠日: 2026-08-25
- 対象: DATA LABにおけるDMM/FANZA API由来情報の利用・表示判断
- 非対象: Publication Gate変更、production integration、lifecycle判定、sort意味の確定

## 根拠と解釈境界

問い合わせでは、商品タイトル、商品メイン画像URL、商品ページURL、メーカー・シリーズ・出演者・ジャンル、価格・レビュー数値、独自の価格比較・ranking・分析結果の表示可否を確認した。DMMアフィリエイトサポートから「記載いただいている情報のいずれも、ご利用いただいて問題ございません」と回答を受領した、という対応関係を本policyの前提とする。

本policyは法的助言ではなく、受領回答と問い合わせ内容を対応付けた内部decision recordである。将来回答やガイドラインが変わる場合はversionを上げ、既存decisionをsilent overwriteしない。

Evidence typeは次の3種だけを使う。

- `DIRECT_SUPPORT_CONFIRMATION`: 問い合わせ項目とサポート回答の直接対応、または回答で明示された対象外例
- `USER_DECLARED_NON_USE`: 問い合わせ時にDATA LAB側が明示した非利用方針
- `SEPARATE_POLICY_PENDING`: 今回の回答だけでは表示条件または意味を確定しない

## Decision states

- `APPROVED`: 記載scope内で表示可能と判断
- `PROHIBITED`: public dataまたは表示に使用しない
- `CONDITIONALLY_APPROVED`: 指定用途・別policy成立時だけ利用可能。一般public fieldとしては未承認
- `PENDING_SEPARATE_POLICY`: 今回の根拠では確定せず、別policyが必要
- `NOT_APPLICABLE`: そのdecision軸を適用しない

## Decision matrix

| Field | Public decision | Semantic decision | Evidence | Scope / condition |
|---|---|---|---|---|
| title | APPROVED | NOT_APPLICABLE | DIRECT_SUPPORT_CONFIRMATION | API取得の商品タイトル |
| product_main_image | APPROVED | NOT_APPLICABLE | DIRECT_SUPPORT_CONFIRMATION | FANZA対象商品API由来の商品メイン画像のみ |
| dmm_books_product_image | PROHIBITED | NOT_APPLICABLE | DIRECT_SUPPORT_CONFIRMATION | DMM Booksの商品画像へ一般化しない |
| product_page_url | APPROVED | NOT_APPLICABLE | DIRECT_SUPPORT_CONFIRMATION | API取得の商品ページURL |
| maker / series / actress_name / genre | APPROVED | NOT_APPLICABLE | DIRECT_SUPPORT_CONFIRMATION | 名称情報。人物画像は含まない |
| price / review_count / review_average | APPROVED | NOT_APPLICABLE | DIRECT_SUPPORT_CONFIRMATION | 比較・分析目的の数値情報 |
| derived_price_comparison / derived_ranking / derived_analysis | APPROVED | NOT_APPLICABLE | DIRECT_SUPPORT_CONFIRMATION | 独自集計に限定し、公式結果と誤認させない |
| product_description / user_review_text | PROHIBITED | NOT_APPLICABLE | USER_DECLARED_NON_USE | 紹介文・レビュー本文を転載しない |
| actress_api_face_image | PROHIBITED | NOT_APPLICABLE | DIRECT_SUPPORT_CONFIRMATION | 女優API由来の顔写真 |
| person_list_image / sample_video / video_capture | PROHIBITED | NOT_APPLICABLE | USER_DECLARED_NON_USE | 問い合わせ時の非利用方針 |
| raw_api_response | PROHIBITED | NOT_APPLICABLE | USER_DECLARED_NON_USE | raw responseを公開しない |
| api_id / affiliate_id | PROHIBITED | NOT_APPLICABLE | USER_DECLARED_NON_USE | credential。ブラウザ側にも置かない |
| affiliate_url | CONDITIONALLY_APPROVED | NOT_APPLICABLE | SEPARATE_POLICY_PENDING | 公開JSONは禁止。Web UIリンク生成用途は別policyで扱う |
| query_context | PROHIBITED | NOT_APPLICABLE | USER_DECLARED_NON_USE | 内部監査専用。public dataは禁止 |
| lifecycle_status / API 0件 / sale ended / unpublished / deleted / affiliate ineligible / affiliateURL有無の意味 | PENDING_SEPARATE_POLICY | PENDING_SEPARATE_POLICY | SEPARATE_POLICY_PENDING | lifecycle policyで判断 |
| rank_sort_semantics / review_sort_semantics | PENDING_SEPARATE_POLICY | PENDING_SEPARATE_POLICY | SEPARATE_POLICY_PENDING | sort意味の公式定義は今回確定しない |

## 独自rankingの安全条件

独自rankingには、自社定義、算出根拠、対象population、更新時刻、データ出典、広告・PR／affiliate表示を明示する。`source_position`をglobal rankとして表示してはならず、DMM公式rankingと誤認させない。表示可能という判断は、rank sortの意味を公式に確定するものではない。

## Publication Gateとの将来mapping

現在rights review pendingの `title`、`image_url`（本matrixの`product_main_image`）、`item_url`（`product_page_url`）、`maker`、`series`、`actress`（`actress_name`）、`genre` は、本matrix上では将来のallowlist候補である。`price`、`review_count`、`review_average`、独自の価格比較・ranking・analysisも候補にできる。ただし、本変更ではPublication GateおよびPublic Data builderへ接続しない。

## 必須のsemantic separation

- 表示許可はlifecycle判定許可ではない。
- 表示許可はsort意味の公式定義ではない。
- 独自rankingの許可はDMM公式rankingを名乗れることを意味しない。
- `actress_name`の許可はactress face imageの許可ではない。
- FANZA対象商品のproduct image許可はDMM Books imageの許可ではない。
- APIで取得可能であることだけでは再表示可能と判断しない。

## 運用条件

affiliate linkには広告・PR表示を付ける。lifecycle対象商品は別policyに基づいて定期確認し、必要に応じ掲載停止またはリンク削除を行う。根拠追加・回答変更・ガイドライン変更時は新versionで再評価する。
