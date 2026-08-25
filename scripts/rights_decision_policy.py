"""Pure DATA LAB rights decision matrix.

This module is deliberately not integrated with the Publication Gate or any
production path.  It records display decisions separately from semantic
interpretation decisions and fails closed for unknown fields.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType


POLICY_VERSION = "0.1"

APPROVED = "APPROVED"
PROHIBITED = "PROHIBITED"
NOT_APPLICABLE = "NOT_APPLICABLE"
PENDING_SEPARATE_POLICY = "PENDING_SEPARATE_POLICY"
CONDITIONALLY_APPROVED = "CONDITIONALLY_APPROVED"

DIRECT_SUPPORT_CONFIRMATION = "DIRECT_SUPPORT_CONFIRMATION"
USER_DECLARED_NON_USE = "USER_DECLARED_NON_USE"
SEPARATE_POLICY_PENDING = "SEPARATE_POLICY_PENDING"

DECISION_STATES = frozenset(
    {APPROVED, PROHIBITED, NOT_APPLICABLE, PENDING_SEPARATE_POLICY, CONDITIONALLY_APPROVED}
)
EVIDENCE_TYPES = frozenset(
    {DIRECT_SUPPORT_CONFIRMATION, USER_DECLARED_NON_USE, SEPARATE_POLICY_PENDING}
)


@dataclass(frozen=True)
class RightsDecision:
    field: str
    public_display: str
    semantic_status: str
    evidence_type: str
    scope: str
    future_public_data_candidate: bool = False
    secret_bearing: bool = False


def _row(
    field: str,
    public_display: str,
    evidence_type: str,
    scope: str,
    *,
    semantic_status: str = NOT_APPLICABLE,
    candidate: bool = False,
    secret: bool = False,
) -> RightsDecision:
    return RightsDecision(
        field, public_display, semantic_status, evidence_type, scope, candidate, secret
    )


_ROWS = (
    _row("title", APPROVED, DIRECT_SUPPORT_CONFIRMATION, "API取得の商品タイトル", candidate=True),
    _row("product_main_image", APPROVED, DIRECT_SUPPORT_CONFIRMATION, "FANZA対象商品API由来の商品メイン画像に限定", candidate=True),
    _row("dmm_books_product_image", PROHIBITED, DIRECT_SUPPORT_CONFIRMATION, "DMM Booksの商品画像は対象外"),
    _row("product_page_url", APPROVED, DIRECT_SUPPORT_CONFIRMATION, "API取得の商品ページURL", candidate=True),
    _row("maker", APPROVED, DIRECT_SUPPORT_CONFIRMATION, "API取得のメーカー名", candidate=True),
    _row("series", APPROVED, DIRECT_SUPPORT_CONFIRMATION, "API取得のシリーズ名", candidate=True),
    _row("actress_name", APPROVED, DIRECT_SUPPORT_CONFIRMATION, "API取得の出演者名（画像を含まない）", candidate=True),
    _row("genre", APPROVED, DIRECT_SUPPORT_CONFIRMATION, "API取得のジャンル名", candidate=True),
    _row("price", APPROVED, DIRECT_SUPPORT_CONFIRMATION, "比較・分析目的の数値", candidate=True),
    _row("review_count", APPROVED, DIRECT_SUPPORT_CONFIRMATION, "レビュー件数の数値", candidate=True),
    _row("review_average", APPROVED, DIRECT_SUPPORT_CONFIRMATION, "レビュー平均点の数値", candidate=True),
    _row("derived_price_comparison", APPROVED, DIRECT_SUPPORT_CONFIRMATION, "独自集計。算出根拠等の表示条件に従う", candidate=True),
    _row("derived_ranking", APPROVED, DIRECT_SUPPORT_CONFIRMATION, "独自rankingに限定。DMM公式rankingを名乗らない", candidate=True),
    _row("derived_analysis", APPROVED, DIRECT_SUPPORT_CONFIRMATION, "独自集計・分析結果", candidate=True),
    _row("product_description", PROHIBITED, USER_DECLARED_NON_USE, "商品紹介文を転載しない"),
    _row("user_review_text", PROHIBITED, USER_DECLARED_NON_USE, "ユーザーレビュー本文を転載しない"),
    _row("actress_api_face_image", PROHIBITED, DIRECT_SUPPORT_CONFIRMATION, "女優API由来の顔写真"),
    _row("person_list_image", PROHIBITED, USER_DECLARED_NON_USE, "女優一覧・人物一覧等由来の人物写真"),
    _row("sample_video", PROHIBITED, USER_DECLARED_NON_USE, "サンプル動画"),
    _row("video_capture", PROHIBITED, USER_DECLARED_NON_USE, "動画キャプチャ"),
    _row("raw_api_response", PROHIBITED, USER_DECLARED_NON_USE, "raw API response"),
    _row("api_id", PROHIBITED, USER_DECLARED_NON_USE, "credential", secret=True),
    _row("affiliate_id", PROHIBITED, USER_DECLARED_NON_USE, "credential", secret=True),
    _row("affiliate_url", CONDITIONALLY_APPROVED, SEPARATE_POLICY_PENDING, "公開JSONは禁止。Web UIリンク生成用途のみ別policyで判断"),
    _row("query_context", PROHIBITED, USER_DECLARED_NON_USE, "内部監査専用。public dataへの収録は禁止"),
    _row("lifecycle_status", PENDING_SEPARATE_POLICY, SEPARATE_POLICY_PENDING, "表示許可からlifecycle状態を推定しない", semantic_status=PENDING_SEPARATE_POLICY),
    _row("api_zero_result_meaning", PENDING_SEPARATE_POLICY, SEPARATE_POLICY_PENDING, "API 0件の意味", semantic_status=PENDING_SEPARATE_POLICY),
    _row("sale_ended", PENDING_SEPARATE_POLICY, SEPARATE_POLICY_PENDING, "販売終了判定", semantic_status=PENDING_SEPARATE_POLICY),
    _row("unpublished", PENDING_SEPARATE_POLICY, SEPARATE_POLICY_PENDING, "非公開判定", semantic_status=PENDING_SEPARATE_POLICY),
    _row("deleted", PENDING_SEPARATE_POLICY, SEPARATE_POLICY_PENDING, "削除判定", semantic_status=PENDING_SEPARATE_POLICY),
    _row("affiliate_ineligible", PENDING_SEPARATE_POLICY, SEPARATE_POLICY_PENDING, "アフィリエイト対象外判定", semantic_status=PENDING_SEPARATE_POLICY),
    _row("affiliate_url_presence_meaning", PENDING_SEPARATE_POLICY, SEPARATE_POLICY_PENDING, "affiliateURL有無の意味", semantic_status=PENDING_SEPARATE_POLICY),
    _row("rank_sort_semantics", PENDING_SEPARATE_POLICY, SEPARATE_POLICY_PENDING, "rank sortの意味は公式定義未確定", semantic_status=PENDING_SEPARATE_POLICY),
    _row("review_sort_semantics", PENDING_SEPARATE_POLICY, SEPARATE_POLICY_PENDING, "review sortの意味は公式定義未確定", semantic_status=PENDING_SEPARATE_POLICY),
)

RIGHTS_DECISIONS = MappingProxyType({row.field: row for row in _ROWS})
SECRET_BEARING_FIELDS = frozenset({row.field for row in _ROWS if row.secret_bearing})


def decision_for(field: str) -> RightsDecision:
    """Return a known decision; unknown fields fail closed."""

    if not isinstance(field, str) or field not in RIGHTS_DECISIONS:
        raise KeyError("UNKNOWN_RIGHTS_FIELD")
    return RIGHTS_DECISIONS[field]


def validate_policy() -> tuple[str, ...]:
    errors: list[str] = []
    if POLICY_VERSION != "0.1":
        errors.append("POLICY_VERSION_INVALID")
    if len(RIGHTS_DECISIONS) != len(_ROWS):
        errors.append("DUPLICATE_FIELD")
    for row in _ROWS:
        if row.public_display not in DECISION_STATES or row.semantic_status not in DECISION_STATES:
            errors.append("UNKNOWN_DECISION_STATE")
        if row.evidence_type not in EVIDENCE_TYPES:
            errors.append("UNKNOWN_EVIDENCE_TYPE")
        if row.secret_bearing and row.public_display in {APPROVED, CONDITIONALLY_APPROVED}:
            errors.append("SECRET_BEARING_FIELD_APPROVED")
        if row.public_display == APPROVED and row.evidence_type == SEPARATE_POLICY_PENDING:
            errors.append("PENDING_EVIDENCE_APPROVED")
    return tuple(sorted(set(errors)))


__all__ = [
    "APPROVED", "CONDITIONALLY_APPROVED", "DECISION_STATES",
    "DIRECT_SUPPORT_CONFIRMATION", "EVIDENCE_TYPES", "NOT_APPLICABLE",
    "PENDING_SEPARATE_POLICY", "POLICY_VERSION", "PROHIBITED",
    "RIGHTS_DECISIONS", "RightsDecision", "SECRET_BEARING_FIELDS",
    "SEPARATE_POLICY_PENDING", "USER_DECLARED_NON_USE", "decision_for",
    "validate_policy",
]
