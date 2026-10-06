"""Build the next minimal, non-sending BOOKS compliance follow-up packet."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import ebook_bl_compliance_questionnaire as ebook_bl


VERSION = "0.1"
READY = "READY_FOR_MANUAL_SEND_REVIEW"


@dataclass(frozen=True)
class FollowupQuestion:
    question_id: str
    scope: str
    prompt_ja: str


@dataclass(frozen=True)
class BooksNextComplianceFollowupPacket:
    version: str
    status: str
    subject_ja: str
    introduction_ja: str
    questions: tuple[FollowupQuestion, ...]
    closing_ja: str
    question_count: int
    send_authorized: bool
    external_send_performed: bool
    compliance_approved: bool
    publication_allowed: bool
    affiliate_allowed: bool
    production_write_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["questions"] = [asdict(row) for row in self.questions]
        value["reason_codes"] = list(self.reason_codes)
        return value


EBOOK_COMIC_RESIDUAL = FollowupQuestion(
    "EBOOK_COMIC_CONTRIBUTOR_DISPLAY_PERMISSION",
    "FANZA/ebook/comic/ebook_comic",
    (
        "前回、商品情報APIのiteminfoにあるauthorは作者名、manufactureは出版社名を"
        "表すとのご回答をいただきました。これらのAPI取得名称を、承認済みサイト上で"
        "作者名・出版社名として表示して問題ありませんか。表示上の追加条件があれば"
        "併せてご教示ください。"
    ),
)


def build() -> BooksNextComplianceFollowupPacket:
    bl_questions = tuple(
        FollowupQuestion(row.question_id, "FANZA/ebook/BL", row.prompt_ja)
        for row in ebook_bl.QUESTIONS
    )
    questions = (EBOOK_COMIC_RESIDUAL, *bl_questions)
    question_ids = tuple(row.question_id for row in questions)
    if len(question_ids) != 5 or len(question_ids) != len(set(question_ids)):
        raise ValueError("BOOKS_NEXT_FOLLOWUP_SCOPE_INVALID")
    return BooksNextComplianceFollowupPacket(
        VERSION,
        READY,
        "FANZA電子コミックおよび電子書籍BLのAPIデータ表示範囲についての確認",
        (
            "承認済みサイトで商品情報APIのデータを扱う準備をしています。"
            "既存回答を別の対象へ推測適用しないため、未確認の項目のみご確認ください。"
        ),
        questions,
        "対象外または個別判断となる項目は、その旨をご回答いただけますと幸いです。",
        len(questions),
        False,
        False,
        False,
        False,
        False,
        False,
        (
            "ONE_EBOOK_COMIC_RESIDUAL_QUESTION_ONLY",
            "FOUR_EXACT_EBOOK_BL_SCOPE_QUESTIONS",
            "NO_CROSS_CATEGORY_INFERENCE",
            "MANUAL_REVIEW_REQUIRED_BEFORE_SEND",
            "NO_EXTERNAL_SEND",
            "PUBLICATION_REMAINS_CLOSED",
        ),
    )


if __name__ == "__main__":
    import json

    print(json.dumps(build().to_dict(), ensure_ascii=False, sort_keys=True))
