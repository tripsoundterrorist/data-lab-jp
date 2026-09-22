"""Pure offline presentation only; no click-time check, redirect, or LIVE use."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
from html import escape
import re
from typing import Any

import affiliate_cta_presentation as presentation

SELECTION_DIGEST = "ba7cbba3e5831ed8a26f25653db0865672b236ed96b372ea93877bdcdf5aac0b"
PUBLIC_ID = re.compile(r"itm_[0-9a-f]{24}\Z")
MAX_AGE = timedelta(minutes=15)

@dataclass(frozen=True)
class CandidateResult:
    html: str
    rendered_count: int
    cta_count: int
    publication_allowed: bool = False
    affiliate_eligibility_allowed: bool = False
    gate_mutation_allowed: bool = False
    cta_activation_allowed: bool = False

def render(records: Any, *, selection_digest: Any, as_of: Any) -> CandidateResult:
    """Render fixtures only; redirect authorization requires a separate contract."""
    if (selection_digest != SELECTION_DIGEST or not isinstance(as_of, datetime)
            or as_of.tzinfo is None or type(records) is not tuple
            or not 1 <= len(records) <= 10):
        raise ValueError("CANARY_INPUT_INVALID")
    cards=[]
    for record in records:
        if (type(record) is not dict or set(record) != {"public_id", "title", "observed_at", "fresh", "revalidation_status"}
                or type(record["public_id"]) is not str or PUBLIC_ID.fullmatch(record["public_id"]) is None
                or type(record["title"]) is not str or not record["title"]
                or type(record["fresh"]) is not bool or type(record["revalidation_status"]) is not str
                or not isinstance(record["observed_at"], datetime) or record["observed_at"].tzinfo is None):
            raise ValueError("CANARY_RECORD_INVALID")
        observed=record["observed_at"]
        eligible=(record["fresh"] and record["revalidation_status"] == "API_VISIBLE_AFFILIATE_PRESENT"
                  and isinstance(observed, datetime) and observed.tzinfo is not None
                  and timedelta(0) <= as_of-observed <= MAX_AGE)
        title=escape(record["title"])
        if eligible:
            cards.append(f'<article><h2>{title}</h2><p>{presentation.DISCLOSURE_TEXT}</p><a href="/go/{record["public_id"]}">{presentation.CTA_LABEL}</a></article>')
        else:
            cards.append(f'<article><h2>{title}</h2></article>')
    html="<main>"+"".join(cards)+"</main>"
    return CandidateResult(html, len(records), sum('href="/go/' in card for card in cards))
