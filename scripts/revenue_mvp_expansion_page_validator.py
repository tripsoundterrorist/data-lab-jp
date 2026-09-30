"""Pure page-boundary validator for a future isolated 300-item collection."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


VERSION = "0.1"
EXPECTED_HITS = 50
EXPECTED_OFFSETS = (1, 51, 101, 151, 201, 251)
EXPECTED_TOTAL = 300
PASS = "PASS"
BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class PageObservation:
    offset: int
    requested_hits: int
    result_count: int
    content_ids: tuple[str, ...]


@dataclass(frozen=True)
class PageValidation:
    version: str
    status: str
    page_count: int
    item_count: int
    unique_item_count: int
    database_write_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def validate(pages: Any) -> PageValidation:
    if type(pages) is not tuple or any(type(page) is not PageObservation for page in pages):
        return PageValidation(VERSION, BLOCKED, 0, 0, 0, False, ("PAGE_CONTRACT_INVALID",))

    reasons: set[str] = set()
    if len(pages) != len(EXPECTED_OFFSETS):
        reasons.add("PAGE_COUNT_NOT_EXACT")
    if tuple(page.offset for page in pages) != EXPECTED_OFFSETS:
        reasons.add("OFFSET_SEQUENCE_INVALID")

    all_ids: list[str] = []
    for page in pages:
        if type(page.offset) is not int or type(page.requested_hits) is not int or type(page.result_count) is not int:
            reasons.add("PAGE_NUMERIC_FIELD_INVALID")
            continue
        if page.requested_hits != EXPECTED_HITS:
            reasons.add("REQUEST_HITS_NOT_EXACT")
        if page.result_count != EXPECTED_HITS or len(page.content_ids) != EXPECTED_HITS:
            reasons.add("PAGE_RESULT_COUNT_NOT_EXACT")
        if any(type(value) is not str or not value.strip() for value in page.content_ids):
            reasons.add("CONTENT_ID_INVALID")
        all_ids.extend(page.content_ids)

    unique = len(set(all_ids))
    if len(all_ids) != EXPECTED_TOTAL:
        reasons.add("TOTAL_ITEM_COUNT_NOT_EXACT")
    if unique != len(all_ids):
        reasons.add("DUPLICATE_CONTENT_ID_ACROSS_PAGES")

    ready = not reasons
    return PageValidation(
        VERSION, PASS if ready else BLOCKED, len(pages), len(all_ids), unique,
        ready, tuple(sorted(reasons)),
    )


__all__ = ["PageObservation", "PageValidation", "validate"]
