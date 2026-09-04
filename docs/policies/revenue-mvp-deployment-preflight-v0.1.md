# Revenue MVP Deployment Preflight v0.1

公開シェルと、任意指定されたPublic Data candidateを配備前に分離検証する非配備Gate。Cloudflare、GitHub、本番URL、DB、repository内容を変更せず、外部通信もしない。

## 現在の判定

商品データを指定しない場合、現行19ファイルのallowlist、秘密情報検査、canonical、404 noindex、Privacy、同意前GA4 block、robots、sitemapを検査する。合格結果は`SHELL_VALIDATED`であり、`deployment_preflight=NOT_EVALUATED_NO_PUBLIC_DATA`、`public_data_deployment_allowed=false`とする。

## Public Data candidate

candidateはOS temp root配下の明示directoryだけをread-onlyで受け付ける。symlink、JSON以外、未知field、secret/path、digest不整合、closed Publication Gateはfail-closedとなる。`artifact_validation=PASS`だけでは配備できず、validatorの`publication_allowed=true`も同時に必要とする。

結果は件数とstatusだけを返し、ファイル内容、商品名、URL、public ID、DB path、credential、raw exceptionを出力しない。production deployやPublication Activationは別commitと明示承認を必要とする。
