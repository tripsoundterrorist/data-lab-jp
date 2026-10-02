"""Fixed, non-sending routing for doujin compliance review questions."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from doujin_compliance_handoff import QUESTION_IDS


VERSION = "0.1"
DMM_SUPPORT = "DMM_AFFILIATE_SUPPORT_REVIEW"
INTERNAL = "DATA_LAB_INTERNAL_COMPLIANCE_REVIEW"


@dataclass(frozen=True)
class ReviewQuestion:
    question_id: str
    owner: str
    prior_evidence_candidate: bool
    prompt_ja: str


@dataclass(frozen=True)
class DoujinComplianceQuestionnaire:
    version: str
    status: str
    questions: tuple[ReviewQuestion, ...]
    external_send_performed: bool
    publication_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["questions"] = [asdict(row) for row in self.questions]
        value["reason_codes"] = list(self.reason_codes)
        return value


QUESTIONS = (
    ReviewQuestion(
        "DOUJIN_SOURCE_SCOPE_APPLICABILITY", DMM_SUPPORT, True,
        "既存のAPI取得情報の表示可否に関する回答は、FANZA同人・BL同人・TL同人の商品情報にも適用されますか。",
    ),
    ReviewQuestion(
        "RELEASE_DATE_PUBLIC_DISPLAY", DMM_SUPPORT, False,
        "商品情報APIから取得した発売日を、対象商品ページで表示して問題ありませんか。",
    ),
    ReviewQuestion(
        "LIST_PRICE_PUBLIC_DISPLAY", DMM_SUPPORT, True,
        "商品情報APIから取得した定価を、現在価格や割引情報とともに表示して問題ありませんか。",
    ),
    ReviewQuestion(
        "OBSERVATION_TIME_PUBLIC_DISPLAY", INTERNAL, False,
        "DATA LABが取得した観測時刻を、公式更新時刻と誤認させない表示として採用するか。",
    ),
    ReviewQuestion(
        "DATA_FRESHNESS_PUBLIC_DISPLAY", INTERNAL, False,
        "取得時刻に基づく鮮度表示の閾値・文言・期限切れ時の非表示条件をどう定義するか。",
    ),
    ReviewQuestion(
        "SANITIZED_RAW_RETENTION_ALLOWED", DMM_SUPPORT, False,
        "認証情報とアフィリエイトURLを除外した商品情報APIレスポンスを、非公開環境で履歴保存して問題ありませんか。",
    ),
    ReviewQuestion(
        "SANITIZED_RAW_RETENTION_DURATION", DMM_SUPPORT, False,
        "非公開で履歴保存できる場合、保存期間または削除時期に指定はありますか。",
    ),
    ReviewQuestion(
        "HISTORICAL_NORMALIZED_PRICE_RETENTION", DMM_SUPPORT, False,
        "APIから取得した価格を正規化した履歴データとして保持し、価格推移の表示に利用して問題ありませんか。",
    ),
    ReviewQuestion(
        "PRODUCT_REMOVAL_RETENTION", DMM_SUPPORT, True,
        "商品がAPIで取得できなくなった場合、過去データの保持・非公開化・削除について必要な対応はありますか。",
    ),
    ReviewQuestion(
        "API_VISIBLE_AFFILIATE_ELIGIBILITY", DMM_SUPPORT, True,
        "FANZA同人のAPI取得可能商品をアフィリエイト対象として扱う際、追加で確認すべき条件はありますか。",
    ),
    ReviewQuestion(
        "API_INVISIBLE_PUBLICATION_ACTION", DMM_SUPPORT, True,
        "FANZA同人の商品がAPIで取得できなくなった場合、商品情報とリンクを非公開または削除する運用で問題ありませんか。",
    ),
    ReviewQuestion(
        "PREORDER_AVAILABILITY_SEMANTICS", DMM_SUPPORT, True,
        "予約商品・在庫なし等のAPI表示を、その状態を明示して掲載する運用で問題ありませんか。",
    ),
    ReviewQuestion(
        "DOUJIN_MAIN_IMAGE_DISPLAY_REQUIREMENTS", DMM_SUPPORT, True,
        "FANZA同人の商品情報API由来メイン画像の表示について、サイズ・加工・リンク先等の追加条件はありますか。",
    ),
    ReviewQuestion(
        "DOUJIN_DEEPLINK_AFFILIATE_METHOD", DMM_SUPPORT, True,
        "FANZA同人の商品別リンクで公式affiliate URLを使用する運用に、追加条件はありますか。",
    ),
)


def build() -> DoujinComplianceQuestionnaire:
    if tuple(row.question_id for row in QUESTIONS) != QUESTION_IDS:
        raise ValueError("QUESTION_SET_DRIFT")
    return DoujinComplianceQuestionnaire(
        VERSION, "READY_FOR_MANUAL_REVIEW", QUESTIONS, False, False,
        (
            "QUESTIONS_ROUTED_BY_OWNER",
            "PRIOR_EVIDENCE_REVIEW_PRECEDES_RECONTACT",
            "NO_EXTERNAL_SEND",
            "PUBLICATION_REMAINS_CLOSED",
        ),
    )


if __name__ == "__main__":
    import json

    print(json.dumps(build().to_dict(), ensure_ascii=False, sort_keys=True))
