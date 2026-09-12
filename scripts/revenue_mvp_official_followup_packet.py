"""Bounded, send-ready questions for the remaining DMM official blockers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Any

import official_response_intake as intake
from official_blocker_policy import LIFECYCLE_BLOCKER, SORT_BLOCKER


VERSION = "0.1"


@dataclass(frozen=True)
class FollowupSection:
    blocker_id: str
    question_ids: tuple[str, ...]
    questions: tuple[str, ...]


@dataclass(frozen=True)
class OfficialFollowupPacket:
    version: str
    subject: str
    introduction: str
    sections: tuple[FollowupSection, ...]
    closing: str
    gate_unlock_allowed: bool
    send_authorized: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["sections"] = [asdict(section) for section in self.sections]
        value["reason_codes"] = list(self.reason_codes)
        return value


LIFECYCLE_QUESTIONS = (
    "商品をcontent_id（CID）指定でItemList照会した際に0件となった場合、販売終了・非公開・削除・一時的なAPI非表示など、どの状態として扱えますか。0件だけでは状態を特定できない場合は、その旨をご教示ください。",
    "ItemListに商品が返ることは、現在購入可能であることを意味しますか。意味しない場合、購入可否の判定に利用できる公式項目をご教示ください。",
    "以前取得できた商品がItemListに返らなくなった場合、公開ページと過去の価格・ランキング履歴は残してよいですか。必要な非表示・削除条件があればご教示ください。",
    "affiliateURLの有無は、アフィリエイト対象可否または購入可否を意味しますか。リンクを掲載停止・削除すべき公式条件もご教示ください。",
    "取得済み商品について、状態確認のためcontent_id指定で定期的に再照会する運用は推奨または許可されますか。推奨頻度や注意事項があればご教示ください。",
)

SORT_QUESTIONS = (
    "ItemList APIのsort=rankは、何を基準にどの順序で並ぶ値ですか。『人気順』『売上順』『公式ランキング』など、公開時に使用可能な表現をご教示ください。",
    "ItemList APIのsort=reviewは、何を基準にどの順序で並ぶ値ですか。レビュー平均・レビュー件数など、公開時に使用可能な表現をご教示ください。",
    "offsetおよびレスポンス内の商品位置は、その照会条件における順位として公開してよいですか。それとも単なるレスポンス位置としてのみ扱うべきですか。",
    "sort=rankおよびsort=reviewの並び順は、どの程度の頻度・タイミングで更新されますか。固定された順位履歴として保存・推移表示する際の注意事項があればご教示ください。",
)


def build_packet() -> OfficialFollowupPacket:
    """Return the complete question packet without sending or unlocking a Gate."""
    return OfficialFollowupPacket(
        VERSION,
        "ItemList APIの商品状態およびsortパラメータの仕様確認",
        "DMMアフィリエイトAPIを利用した承認済みサイトの運用について、推測を避けるため以下の仕様をご確認させてください。",
        (
            FollowupSection(
                LIFECYCLE_BLOCKER,
                intake.LIFECYCLE_QUESTION_IDS,
                LIFECYCLE_QUESTIONS,
            ),
            FollowupSection(
                SORT_BLOCKER,
                intake.SORT_QUESTION_IDS,
                SORT_QUESTIONS,
            ),
        ),
        "各項目について、仕様上回答できない場合や個別判断となる場合も、その旨をご回答いただけますと幸いです。",
        False,
        False,
        ("EXTERNAL_SEND_REQUIRES_OPERATOR_ACTION", "RESPONSE_REQUIRES_SANITIZED_INTAKE"),
    )


def main() -> int:
    print(json.dumps(build_packet().to_dict(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
