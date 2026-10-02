"""Minimal, non-sending compliance questionnaire for FANZA ebook comics."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any

import category_collection_health as health
import ebook_comic_rights_scope_audit as rights_audit
import ebook_comic_structure_audit as structure_audit


VERSION = "0.1"
READY = "READY_FOR_MANUAL_COMPLIANCE_REVIEW"
FAIL_CLOSED = "FAIL_CLOSED"


@dataclass(frozen=True)
class EbookComicQuestion:
    question_id: str
    prompt_ja: str


QUESTIONS = (
    EbookComicQuestion(
        "EBOOK_COMIC_SOURCE_SCOPE_APPLICABILITY",
        (
            "これまでに確認済みの商品情報API由来データの表示・比較利用に関する回答は、"
            "FANZA電子書籍のcomicフロアの商品にも適用されますか。対象外または追加条件のある"
            "項目（商品タイトル、商品ページURL、シリーズ、ジャンル、現在価格、レビュー数値、"
            "発売日、定価）があればご教示ください。"
        ),
    ),
    EbookComicQuestion(
        "EBOOK_COMIC_IMAGE_SCOPE_REQUIREMENTS",
        (
            "FANZA電子書籍comicフロアの商品情報APIで取得した商品メイン画像は、"
            "承認済みサイトで表示して問題ありませんか。サイズ、加工、リンク先、"
            "クレジット等の追加条件があればご教示ください。"
        ),
    ),
    EbookComicQuestion(
        "EBOOK_COMIC_CONTRIBUTOR_ROLE_SEMANTICS",
        (
            "商品情報APIのiteminfoにあるauthorおよびmanufactureは、それぞれどの主体を"
            "表す項目ですか。また、取得した名称を作者・提供元等のページ項目として表示して"
            "問題ありませんか。"
        ),
    ),
    EbookComicQuestion(
        "EBOOK_COMIC_RETENTION_SCOPE_APPLICABILITY",
        (
            "API由来情報の保存・更新・削除および価格履歴表示に関する既存回答は、"
            "FANZA電子書籍comicフロアにも適用されますか。sanitized rawデータと正規化した"
            "価格履歴について、保存期間または削除条件の指定があればご教示ください。"
        ),
    ),
)


@dataclass(frozen=True)
class EbookComicComplianceQuestionnaire:
    version: str
    status: str
    item_count: int
    questions: tuple[EbookComicQuestion, ...]
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


def _failed(reason: str) -> EbookComicComplianceQuestionnaire:
    return EbookComicComplianceQuestionnaire(
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


def compose(
    structure: Any,
    rights: Any,
) -> EbookComicComplianceQuestionnaire:
    if (
        type(structure) is not structure_audit.EbookComicStructureAudit
        or type(rights) is not rights_audit.EbookComicRightsScopeAudit
        or structure.status != structure_audit.READY
        or rights.status != rights_audit.READY
        or structure.item_count <= 0
        or structure.entity_semantics_confirmed
        or structure.field_rights_confirmed
        or structure.publication_allowed
        or rights.exact_ebook_comic_scope_confirmed
        or rights.contributor_semantics_confirmed
        or rights.image_scope_confirmed
        or rights.field_rights_confirmed
        or rights.publication_allowed
    ):
        return _failed("EBOOK_COMIC_QUESTIONNAIRE_INPUT_NOT_READY")
    question_ids = tuple(row.question_id for row in QUESTIONS)
    if len(question_ids) != len(set(question_ids)):
        return _failed("EBOOK_COMIC_QUESTION_ID_DUPLICATE")
    return EbookComicComplianceQuestionnaire(
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
            "MINIMAL_EBOOK_COMIC_SCOPE_QUESTIONS_READY",
            "PRIOR_EVIDENCE_NOT_AUTO_APPLIED",
            "MANUAL_REVIEW_REQUIRED_BEFORE_SEND",
            "NO_EXTERNAL_SEND",
            "PUBLICATION_REMAINS_CLOSED",
        ),
    )


def assess(
    database: Path = health.DATABASE,
    config: Path = health.CONFIG,
) -> EbookComicComplianceQuestionnaire:
    try:
        return compose(
            structure_audit.assess(database, config),
            rights_audit.assess(),
        )
    except Exception:
        return _failed("EBOOK_COMIC_COMPLIANCE_QUESTIONNAIRE_ERROR")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build an unsent ebook comic compliance questionnaire."
    )
    parser.add_argument("--database", type=Path, default=health.DATABASE)
    parser.add_argument("--config", type=Path, default=health.CONFIG)
    args = parser.parse_args(argv)
    result = assess(args.database, args.config)
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == READY else 2


if __name__ == "__main__":
    raise SystemExit(main())
