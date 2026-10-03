"""Minimal, non-sending compliance questionnaire for FANZA BL ebooks."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any

import category_collection_health as health
import ebook_bl_rights_scope_audit as rights_audit
import ebook_bl_structure_audit as structure_audit


VERSION = "0.1"
READY = "READY_FOR_MANUAL_COMPLIANCE_REVIEW"
FAIL_CLOSED = "FAIL_CLOSED"


@dataclass(frozen=True)
class EbookBlQuestion:
    question_id: str
    prompt_ja: str


QUESTIONS = (
    EbookBlQuestion(
        "EBOOK_BL_SOURCE_SCOPE_APPLICABILITY",
        (
            "これまでに確認済みの商品情報APIデータの表示・比較利用に関する回答は、"
            "FANZA電子書籍のBLフロアの商品にも適用されますか。対象外または追加条件のある"
            "項目（商品タイトル、商品ページURL、シリーズ、ジャンル、現在価格、レビュー数値、"
            "発売日、定価）があればご教示ください。"
        ),
    ),
    EbookBlQuestion(
        "EBOOK_BL_IMAGE_SCOPE_REQUIREMENTS",
        (
            "FANZA電子書籍BLフロアの商品情報APIで取得した商品メイン画像は、承認済みサイトで"
            "表示して問題ありませんか。サイズ、加工、直リンク、クレジット等の追加条件が"
            "あればご教示ください。"
        ),
    ),
    EbookBlQuestion(
        "EBOOK_BL_CONTRIBUTOR_ROLE_SEMANTICS",
        (
            "商品情報APIのiteminfoにあるauthorおよびmanufactureは、それぞれどの主体を表す"
            "項目ですか。また、取得した名称を作者・提供元等のページ項目として表示して"
            "問題ありませんか。"
        ),
    ),
    EbookBlQuestion(
        "EBOOK_BL_RETENTION_SCOPE_APPLICABILITY",
        (
            "API取得値の保存・更新・削除および価格履歴表示に関する既存回答は、FANZA電子書籍"
            "BLフロアにも適用されますか。sanitized rawデータと正規化した価格履歴について、"
            "保存期間または削除条件の指定があればご教示ください。"
        ),
    ),
)


@dataclass(frozen=True)
class EbookBlComplianceQuestionnaire:
    version: str
    status: str
    item_count: int
    questions: tuple[EbookBlQuestion, ...]
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


def _failed(reason: str) -> EbookBlComplianceQuestionnaire:
    return EbookBlComplianceQuestionnaire(
        VERSION, FAIL_CLOSED, 0, (), 0, False, False, False, False, False,
        False, (reason,),
    )


def compose(structure: Any, rights: Any) -> EbookBlComplianceQuestionnaire:
    if (
        type(structure) is not structure_audit.EbookBlStructureAudit
        or type(rights) is not rights_audit.EbookBlRightsScopeAudit
        or structure.status != structure_audit.READY
        or rights.status != rights_audit.READY
        or structure.item_count <= 0
        or structure.entity_semantics_confirmed
        or structure.field_rights_confirmed
        or structure.publication_allowed
        or rights.exact_ebook_bl_scope_confirmed
        or rights.contributor_semantics_confirmed
        or rights.image_scope_confirmed
        or rights.field_rights_confirmed
        or rights.publication_allowed
    ):
        return _failed("EBOOK_BL_QUESTIONNAIRE_INPUT_NOT_READY")
    question_ids = tuple(row.question_id for row in QUESTIONS)
    if len(question_ids) != len(set(question_ids)):
        return _failed("EBOOK_BL_QUESTION_ID_DUPLICATE")
    return EbookBlComplianceQuestionnaire(
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
            "MINIMAL_EBOOK_BL_SCOPE_QUESTIONS_READY",
            "PRIOR_EVIDENCE_NOT_AUTO_APPLIED",
            "DEFER_UNTIL_CURRENT_INQUIRY_RESPONSE_REVIEWED",
            "MANUAL_REVIEW_REQUIRED_BEFORE_SEND",
            "NO_EXTERNAL_SEND",
            "PUBLICATION_REMAINS_CLOSED",
        ),
    )


def assess(
    database: Path = health.DATABASE,
    config: Path = health.CONFIG,
) -> EbookBlComplianceQuestionnaire:
    try:
        return compose(structure_audit.assess(database, config), rights_audit.assess())
    except Exception:
        return _failed("EBOOK_BL_COMPLIANCE_QUESTIONNAIRE_ERROR")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build an unsent FANZA BL ebook compliance questionnaire."
    )
    parser.add_argument("--database", type=Path, default=health.DATABASE)
    parser.add_argument("--config", type=Path, default=health.CONFIG)
    args = parser.parse_args(argv)
    result = assess(args.database, args.config)
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == READY else 2


if __name__ == "__main__":
    raise SystemExit(main())

