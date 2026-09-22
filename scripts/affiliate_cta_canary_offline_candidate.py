"""Pure offline presentation only; no click-time check, redirect, or LIVE use."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
from html import escape
from typing import Any

import affiliate_cta_presentation as presentation
import affiliate_cta_approved_context as approved_context

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

def render(records: Any, *, as_of: Any) -> CandidateResult:
    """Render fixtures only; redirect authorization requires a separate contract."""
    if (not isinstance(as_of, datetime) or as_of.tzinfo is None or type(records) is not tuple
            or not 1 <= len(records) <= 10):
        raise ValueError("CANARY_INPUT_INVALID")
    context = approved_context.production_context()
    if context is None:
        raise ValueError("APPROVED_CONTEXT_UNAVAILABLE")
    cards=[]
    for record in records:
        if (type(record) is not dict or set(record) != {"public_id", "title", "observed_at", "fresh", "revalidation_status"}
                or not approved_context._context_member(context, record["public_id"])
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
            cards.append(f'<article><h2>{title}</h2><p>{presentation.DISCLOSURE_TEXT}</p><a href="/go/{record["public_id"]}" rel="noopener noreferrer sponsored">{presentation.CTA_LABEL}</a></article>')
        else:
            cards.append(f'<article><h2>{title}</h2></article>')
    html="<main>"+"".join(cards)+"</main>"
    return CandidateResult(html, len(records), sum('href="/go/' in card for card in cards))
