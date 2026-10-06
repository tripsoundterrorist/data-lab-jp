"""Minimal, non-sending compliance questionnaire for DMM photo books."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any

import category_collection_health as health
import photo_book_rights_scope_audit as rights_audit
import photo_book_structure_audit as structure_audit


VERSION = "0.1"
READY = "READY_FOR_MANUAL_COMPLIANCE_REVIEW"
FAIL_CLOSED = "FAIL_CLOSED"


@dataclass(frozen=True)
class PhotoBookQuestion:
    question_id: str
    prompt_ja: str


QUESTIONS = (
    PhotoBookQuestion(
        "PHOTO_BOOK_SOURCE_SCOPE_APPLICABILITY",
        (
            "これまでに確認済みの商品情報API取得データの表示・比較利用に関する回答は、"
            "DMM.com電子書籍のphotoフロア（写真集）にも適用されますか。商品タイトル、"
            "商品ページURL、シリーズ、ジャンル、現在価格、レビュー数値、発売日、定価について、"
            "対象外または追加条件がある項目をご教示ください。"
        ),
    ),
    PhotoBookQuestion(
        "PHOTO_BOOK_IMAGE_PROHIBITION_AND_SCOPE",
        (
            "過去の確認ではDMM Booksの商品画像は使用しない整理となっています。"
            "DMM.com電子書籍のphotoフロア（写真集）で商品情報APIから取得される商品画像も"
            "表示不可という理解で相違ありませんか。表示可能な範囲がある場合は、対象画像、"
            "サイズ、加工、リンク、クレジット等の条件をご教示ください。"
        ),
    ),
    PhotoBookQuestion(
        "PHOTO_BOOK_CONTRIBUTOR_ROLE_SEMANTICS",
        (
            "商品情報APIのiteminfoにあるactor、author、manufactureは、それぞれどの主体を"
            "示す項目ですか。また、取得した値を人物・著者・提供元等のページ項目として表示して"
            "問題ありませんか。"
        ),
    ),
    PhotoBookQuestion(
        "PHOTO_BOOK_RETENTION_SCOPE_APPLICABILITY",
        (
            "API取得項目の保存・更新・削除および価格履歴表示に関する既存回答は、"
            "DMM.com電子書籍のphotoフロア（写真集）にも適用されますか。sanitized rawデータと"
            "正規化した価格履歴について、保存期間または削除条件の指定があればご教示ください。"
        ),
    ),
)


@dataclass(frozen=True)
class PhotoBookComplianceQuestionnaire:
    version: str
    status: str
    item_count: int
    questions: tuple[PhotoBookQuestion, ...]
    question_count: int
    send_authorized: bool
    external_send_performed: bool
    repository_write_performed: bool
    compliance_approved: bool
    publication_allowed: bool
    production_write_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["questions"] = [asdict(row) for row in self.questions]
        result["reason_codes"] = list(self.reason_codes)
        return result


def _failed(reason: str) -> PhotoBookComplianceQuestionnaire:
    return PhotoBookComplianceQuestionnaire(
        VERSION,
        FAIL_CLOSED,
        0,
        (),
        0,
        False,
        False,
        False,
        False,
        False,
        False,
        (reason,),
    )


def compose(structure: Any, rights: Any) -> PhotoBookComplianceQuestionnaire:
    if (
        type(structure) is not structure_audit.PhotoBookStructureAudit
        or type(rights) is not rights_audit.PhotoBookRightsScopeAudit
        or structure.status != structure_audit.READY
        or rights.status != rights_audit.READY
        or structure.item_count <= 0
        or structure.entity_semantics_confirmed
        or structure.field_rights_confirmed
        or structure.publication_allowed
        or rights.exact_photo_book_scope_confirmed
        or rights.contributor_semantics_confirmed
        or rights.image_display_allowed
        or rights.field_rights_confirmed
        or rights.publication_allowed
    ):
        return _failed("PHOTO_BOOK_QUESTIONNAIRE_INPUT_NOT_READY")
    question_ids = tuple(row.question_id for row in QUESTIONS)
    if len(question_ids) != len(set(question_ids)):
        return _failed("PHOTO_BOOK_QUESTION_ID_DUPLICATE")
    return PhotoBookComplianceQuestionnaire(
        VERSION,
        READY,
        structure.item_count,
        QUESTIONS,
        len(QUESTIONS),
        False,
        False,
        False,
        False,
        False,
        False,
        (
            "MINIMAL_PHOTO_BOOK_SCOPE_QUESTIONS_READY",
            "DMM_BOOKS_IMAGE_PROHIBITION_PRESERVED_PENDING_EXPLICIT_UPDATE",
            "PRIOR_EVIDENCE_NOT_AUTO_APPLIED",
            "SEND_DEFERRED_UNTIL_BOOKS_NEXT_RESPONSE_REVIEWED",
            "MANUAL_REVIEW_REQUIRED_BEFORE_SEND",
            "NO_EXTERNAL_SEND",
            "PUBLICATION_REMAINS_CLOSED",
        ),
    )


def assess(
    database: Path = health.DATABASE,
    config: Path = health.CONFIG,
) -> PhotoBookComplianceQuestionnaire:
    try:
        return compose(
            structure_audit.assess(database, config),
            rights_audit.assess(),
        )
    except Exception:
        return _failed("PHOTO_BOOK_COMPLIANCE_QUESTIONNAIRE_ERROR")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build an unsent photo-book compliance questionnaire."
    )
    parser.add_argument("--database", type=Path, default=health.DATABASE)
    parser.add_argument("--config", type=Path, default=health.CONFIG)
    args = parser.parse_args(argv)
    result = assess(args.database, args.config)
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == READY else 2


if __name__ == "__main__":
    raise SystemExit(main())
