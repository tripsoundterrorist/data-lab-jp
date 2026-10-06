"""Minimal, non-sending DMM follow-up packet for doujin compliance scope."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import doujin_compliance_questionnaire as questionnaire
import doujin_prior_evidence_reuse_audit as evidence_audit


VERSION = "0.1"


@dataclass(frozen=True)
class FollowupQuestion:
    question_id: str
    prompt_ja: str


@dataclass(frozen=True)
class DoujinComplianceFollowupPacket:
    version: str
    status: str
    subject_ja: str
    introduction_ja: str
    questions: tuple[FollowupQuestion, ...]
    closing_ja: str
    question_count: int
    send_authorized: bool
    external_send_performed: bool
    publication_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["questions"] = [asdict(row) for row in self.questions]
        value["reason_codes"] = list(self.reason_codes)
        return value


def build() -> DoujinComplianceFollowupPacket:
    audit = evidence_audit.assess()
    if audit.status != evidence_audit.READY:
        raise ValueError("PRIOR_EVIDENCE_AUDIT_NOT_READY")
    by_id = {row.question_id: row for row in questionnaire.QUESTIONS}
    question_ids = audit.recontact_required_ids
    if any(
        question_id not in by_id
        or by_id[question_id].owner != questionnaire.DMM_SUPPORT
        or by_id[question_id].prior_evidence_candidate
        for question_id in question_ids
    ):
        raise ValueError("FOLLOWUP_SCOPE_INVALID")
    questions = tuple(
        FollowupQuestion(question_id, by_id[question_id].prompt_ja)
        for question_id in question_ids
    )
    return DoujinComplianceFollowupPacket(
        VERSION,
        "READY_FOR_MANUAL_SEND_REVIEW",
        "FANZA同人の商品情報APIデータ利用範囲についての確認",
        (
            "承認済みサイトでFANZA同人・BL同人・TL同人の商品情報を、"
            "データ検索・比較・価格推移の用途で扱う準備をしています。"
            "既存回答から推測せず運用するため、未確認の項目のみご確認ください。"
        ),
        questions,
        "回答できない項目や個別判断となる項目は、その旨をご回答いただけますと幸いです。",
        len(questions),
        False,
        False,
        False,
        (
            "MINIMAL_UNRESOLVED_SCOPE_ONLY",
            "SEND_DEFERRED_UNTIL_BOOKS_NEXT_RESPONSE_REVIEWED",
            "MANUAL_REVIEW_REQUIRED_BEFORE_SEND",
            "NO_EXTERNAL_SEND",
            "PUBLICATION_REMAINS_CLOSED",
        ),
    )


if __name__ == "__main__":
    import json

    print(json.dumps(build().to_dict(), ensure_ascii=False, sort_keys=True))
