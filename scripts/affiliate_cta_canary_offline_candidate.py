"""Inert presentation from fixed internal provider records only."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from html import escape
from typing import Any

import affiliate_cta_approved_context as approved_context
import affiliate_cta_click_revalidation_candidate as click
import affiliate_cta_presentation as presentation
import affiliate_cta_production_composition as composition


@dataclass(frozen=True, repr=False)
class CandidateResult:
    html: str
    rendered_count: int
    cta_count: int
    publication_allowed: bool = False
    affiliate_eligibility_allowed: bool = False
    gate_mutation_allowed: bool = False
    cta_activation_allowed: bool = False

    def __repr__(self):
        return "<CandidateResult>"


def render(*, as_of: Any) -> CandidateResult:
    """Render exactly one provider-owned approved selection, or fail closed."""
    if not isinstance(as_of, datetime) or as_of.tzinfo is None:
        raise ValueError("CANARY_INPUT_INVALID")
    try:
        lifecycle = composition.production_provider()
    except Exception:
        raise ValueError("LIFECYCLE_BLOCKED") from None
    if not composition._valid_lifecycle(lifecycle):
        raise ValueError("APPROVED_CONTEXT_UNAVAILABLE")
    context = lifecycle.context
    try:
        records = lifecycle.records(context)
    except Exception:
        raise ValueError("CANARY_PROVIDER_INVALID") from None
    if type(records) is not tuple:
        raise ValueError("CANARY_PROVIDER_INVALID")
    if len(records) != approved_context.EXACT_SELECTION_COUNT:
        raise ValueError("CANARY_SELECTION_INVALID")
    seen: set[str] = set()
    for record in records:
        if type(record) is not approved_context._InternalPresentationRecord:
            raise ValueError("CANARY_RECORD_INVALID")
        if (
            record.public_id in seen
            or not approved_context._context_member(context, record.public_id)
            or record.selection_digest != approved_context._context_digest(context)
            or type(record.title) is not str
            or not record.title
            or not approved_context._observation_bound(record.observation, context, lifecycle.provider)
        ):
            raise ValueError("CANARY_SELECTION_INVALID")
        seen.add(record.public_id)
    if seen != context.public_ids:
        raise ValueError("CANARY_SELECTION_INVALID")
    cards: list[str] = []
    for record in records:
        result = click._decide(
            version=click.VERSION, clicked_public_id=record.public_id, evaluated_at=as_of,
            context=context, observe=lambda _value, value=record.observation: value,
            provider=lifecycle.provider,
        )
        title = escape(record.title)
        if result.status == click.ALLOWED:
            cards.append(f'<article><h2>{title}</h2><p>{presentation.DISCLOSURE_TEXT}</p><a href="/go/{record.public_id}" rel="noopener noreferrer sponsored">{presentation.CTA_LABEL}</a></article>')
        else:
            cards.append(f"<article><h2>{title}</h2></article>")
    html = "<main>" + "".join(cards) + "</main>"
    result = CandidateResult(html, len(records), sum('href="/go/' in card for card in cards))
    if not composition._valid_lifecycle(lifecycle):
        raise ValueError("LIFECYCLE_BLOCKED")
    return result
