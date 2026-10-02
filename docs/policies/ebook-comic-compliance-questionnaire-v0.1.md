# 電子コミックCompliance確認票 v0.1

更新日: 2026-10-02 JST

## 目的

FANZA電子書籍comicフロアについて、既存の公式回答を自動適用せず、公開準備に必要な追加確認を最小4群へまとめる。確認票は非送信であり、送信前に03 COMPLIANCEとユーザーの明示的承認を必要とする。

## 最小確認項目

1. 既存の商品情報API表示・比較利用回答がFANZA電子コミックへ適用されるか。タイトル、URL、series、genre、価格、review、発売日、定価について対象外や追加条件があるか。
2. FANZA電子コミックAPIの商品メイン画像を表示できるか。サイズ、加工、リンク、クレジット等の条件があるか。
3. `author`と`manufacture`の公式な意味および名称表示の可否。
4. 既存の保存・更新・削除・価格履歴回答が電子コミックへ適用されるか。sanitized rawと正規化価格履歴の保存期間・削除条件があるか。

## 安全境界

- 問い合わせは自動送信しない。
- 既存回答から未確認scopeを推測しない。
- 返信があっても自動的にfield rightsや公開Gateを解除しない。
- 商品情報、URL、価格値、rawレスポンス、秘密情報を確認票へ含めない。
- Production、Publication Gate、affiliate、sitemap、robotsを変更しない。

`READY_FOR_MANUAL_COMPLIANCE_REVIEW`は文面の手動レビュー準備だけを表し、送信・Compliance承認・公開許可を表さない。
