# Revenue MVP DB Audit v0.1

## Purpose

Revenue MVP開始前に、production DBの現在値を読み取り専用で確認する。
商品数、snapshot数、collection run数、最古・最新観測時刻、商品当たり平均観測回数、DBサイズ、integrity、外部キー違反数だけを安全なJSONとして返す。

## Safety boundary

- SQLite URI `mode=ro` と `PRAGMA query_only = ON` を併用する。
- Collector、migration、repair、backup、publicationを実行しない。
- DBパス、商品ID、タイトル、URL、認証情報を出力しない。
- DB欠落、schema不一致、空DB、integrity異常、外部キー違反、観測範囲不明は`BLOCKED`とする。
- `READY`はDB基礎状態の確認だけを意味し、公開許可を与えない。`publication_allowed`は常に`false`。

## Usage

`python scripts/revenue_mvp_db_audit.py`

別DBを明示する場合のみ`--db`を使用する。出力に入力パスは含めない。
