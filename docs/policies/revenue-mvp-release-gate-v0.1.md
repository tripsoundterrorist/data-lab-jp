# Revenue MVP Release Gate v0.1

`scripts/revenue_mvp_release_gate.py` は、静的shell、任意のPublic Data候補、
公式確認、Publication Gateを一つのread-only結果へ集約する。ビルド、配備、
公開状態変更、URL出力は行わない。

データ候補が検証済みでも、DMM/FANZAのlifecycleまたはsort semanticsが未解決なら
`BLOCKED`を維持する。全条件が揃った場合も結果は
`READY_FOR_RELEASE_APPROVAL`までであり、`production_release_allowed`は常にfalse。
本番反映には別の明示承認が必要となる。
