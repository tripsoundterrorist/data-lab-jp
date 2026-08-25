# DATA LAB DMM Official Response Intake v0.1

`intake_version=0.1`。DMM/FANZAの公式回答をraw emailではなくsanitized structured observationとして分類するpure layerである。Gmail、filesystem、API、DBには接続せず、RegistryやGateを変更しない。

許可する根拠は`DIRECT_SUPPORT_CONFIRMATION`と`OFFICIAL_DOCUMENTATION`のみ。internal validation、SDK comment、第三者blog/forum/Reddit、観測API挙動、推測だけでは公式blockerの解除candidateにしない。

LifecycleはCID 0件、visible/invisible、affiliateURL有無、periodic re-query、非表示後のpage/link、履歴metadataの9 question IDを追跡する。Sortはrank/review定義・ordering、offset、position、public expression、update behaviorの8 question IDを追跡する。一部回答は`PARTIALLY_RESOLVED`でunlock false、重大な曖昧さや過去回答との矛盾は`CONTRADICTORY`、manual review requiredとする。

全questionが公式根拠で明示的にRESOLVEDした場合でも返すのは`gate_unlock_candidate=true`までである。blocker RESOLVED、Lifecycle/Semantics Gate PASSは別commit・別reviewで行う。

Rightsは既にresolvedのため、同内容はduplicate confirmationとして扱う。矛盾する公式回答は自動上書きせずmanual reviewへ送る。

safe resultにはraw email、sender個人情報、email address、URL、credential、API/affiliate ID、absolute path、raw exceptionを含めない。
