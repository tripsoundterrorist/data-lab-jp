# DATA LAB Official Blocker Registry v0.1

- `registry_version`: `0.1`
- 対象: DMM/FANZA公式確認待ち事項とPublication Activation内部承認
- 現在状態: **RIGHTS CLEARED BUT NOT PUBLICATION READY**

Publication Gate v0.2のRights GateとData Policy Gateは`PASS`だが、Lifecycle GateとSemantics Gateは`PENDING_OFFICIAL_CONFIRMATION`、Publication Status Gateは`CLOSED`であり、`overall_eligible=false`を維持する。本registryはGateを自動変更しない。

## Blocker一覧

| blocker_id | status | affected_gate | gate_unlock_allowed |
|---|---|---|---:|
| `DMM_LIFECYCLE_AVAILABILITY` | `PENDING_OFFICIAL_CONFIRMATION` | `LIFECYCLE_GATE` | false |
| `DMM_SORT_SEMANTICS` | `PENDING_OFFICIAL_CONFIRMATION` | `SEMANTICS_GATE` | false |
| `PUBLICATION_ACTIVATION` | `INTERNAL_APPROVAL_REQUIRED` | `PUBLICATION_STATUS_GATE` | false |

## DMM_LIFECYCLE_AVAILABILITY

未解決事項は、CID指定ItemListの0件、sale ended・unpublished・deleted・affiliate ineligible・一時的API非表示の区別、affiliateURL有無の意味、定期CID再照会、API非表示後の履歴表示、affiliate link削除条件、使用可能な公式lifecycle signalである。

解除には公式回答から最低限、ItemList/CID結果のavailability解釈、0件の変換可否、affiliateURLとeligibilityの関係、定期再照会の推奨運用、API非表示時のpublic pageとaffiliate linkの扱いが明確になる必要がある。曖昧または部分回答なら`PARTIALLY_RESOLVED`までとし、GateをPASSにしない。

禁止推論:

- 0件からsale endedを推測しない。
- affiliateURLなしからaffiliate ineligibleを推測しない。
- API visibleからcurrently purchasableと断定しない。
- API invisibleからdeletedと断定しない。
- 一定日数未観測からunavailableと断定しない。

## DMM_SORT_SEMANTICS

未解決事項は、`sort=rank`と`sort=review`の公式定義・並び基準、offset/source_positionの意味、query内positionのpublic表現可否、時間更新の挙動である。

解除には公式回答でrank定義、review定義、position/offsetの扱い、許可されるpublic claimが確認される必要がある。一方だけ解決した場合はcomponentを分離し、Semantics Gate全体をPASSにしない。

公式回答前の安全表現は`rank-sorted population`、`review-sorted population`、`query response position`だけとする。売上・人気・総合・市場ranking、review平均順、review件数順への意味変換は禁止する。

## PUBLICATION_ACTIVATION

これはDMM回答待ちではなく内部承認blockerである。Rights、Lifecycle、必要Semantics、Data Policy、public artifact validation、production build、deployment preflightがすべてPASSした後、別commit・別承認でのみ`local_validation_only`から`public`へ変更できる。自動変更しない。

## Evidence policy

許可するevidence typeは`DIRECT_SUPPORT_CONFIRMATION`、`OFFICIAL_DOCUMENTATION`、`INTERNAL_VALIDATION`、`NO_VALID_EVIDENCE`である。DMM公式blockerのRESOLVEDには前二者だけを使用できる。第三者ブログ、SDKコメント、慣例、推測だけではRESOLVEDにしない。evidence referenceにはsecret、個人情報、absolute path、raw email本文を保存しない。

## Resolution順序

1. Lifecycle blockerが公式根拠によりRESOLVEDした後、別変更でLifecycle Gate policyを更新する。
2. Sort blockerが公式根拠により必要componentすべてRESOLVEDした後、別変更でSemantics Gate policyを更新する。
3. 全required gateがPASSした後、Publication Activation Reviewを別commit・別承認で行う。

回答や要件が変わる場合はregistry versionを上げ、既存recordをsilent overwriteしない。
