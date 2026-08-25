# DATA LAB Publication Artifact Validation v0.1

`validator_version=0.1`。Public Data schema/policy 0.1のmanifest、index、detail shardsをproduction公開前にread-onlyで検証する。validatorはpublicationを許可せず、Publication Gateの`overall_eligible`を上書きしない。

既存`build-public-data.py`のallowlist、nested item contract、Public ID `itm_<24hex>`、manifest count、index/detail digestを再利用する。未知field、未知version、malformed JSON、duplicate/missing/orphan detail、forbidden key、secret/path、unsafe URLはfail-closedとする。

URLはHTTP/HTTPSだけを許可し、javascript/data/file、localhost、UNC、credential queryを拒否する。`image_url`のFANZA商品main image provenanceやDMM Books由来かどうかは、現artifact contractにprovenance fieldがないためURL文字列から推測しない。

derived ranking/analysis/review numericはrights上の候補だが、現schemaにmethodology/version、updated_at、population/context contractがないため追加しない。存在した場合は`NOT_IMPLEMENTED_IN_SCHEMA` warningを伴いfail-closedになる。

現在のvalid local fixtureでは`artifact_validation=PASS`かつ、Lifecycle/Semantics/Publication Status Gateが閉じているため`publication_allowed=false`となる。

CLIはOS temp root配下の明示directoryのみをread-onlyで検査する。production `/data`や`dist/data`は生成・変更しない。
