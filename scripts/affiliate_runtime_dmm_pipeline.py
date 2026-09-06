"""Inert composition of the DMM connector and guarded affiliate resolver.

There is no CLI or deployed handler. All policy facts remain explicit inputs.
The existing resolver evaluates blockers before invoking either connector
callback, so a closed gate performs no database lookup or API request.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable
import urllib.request

import affiliate_runtime_dmm_connector as dmm_connector
import affiliate_runtime_resolution as resolution


PIPELINE_VERSION = "0.1"


def run_pipeline(
    *,
    pipeline_version: Any,
    database_path: Path,
    env_path: Path,
    public_id: Any,
    rights_status: Any,
    lifecycle_status: Any,
    verification_status: Any,
    publication_gate_overall_eligible: Any,
    pr_disclosure_available: Any,
    emit_redirect: Callable[[str], None],
    fetcher: Callable[..., Any] = urllib.request.urlopen,
) -> resolution.AffiliateRuntimeResolutionResult:
    """Compose trusted callbacks without exposing identifiers or URLs."""

    if pipeline_version != PIPELINE_VERSION:
        return resolution.resolve_and_deliver_affiliate_link(
            resolution_version="UNSUPPORTED",
            public_id=public_id,
            rights_status=rights_status,
            lifecycle_status=lifecycle_status,
            verification_status=verification_status,
            publication_gate_overall_eligible=publication_gate_overall_eligible,
            pr_disclosure_available=pr_disclosure_available,
            resolve_content_id=lambda _public_id: None,
            fetch_item_response=lambda _content_id: {},
            emit_redirect=emit_redirect,
        )

    return resolution.resolve_and_deliver_affiliate_link(
        resolution_version=resolution.RESOLUTION_VERSION,
        public_id=public_id,
        rights_status=rights_status,
        lifecycle_status=lifecycle_status,
        verification_status=verification_status,
        publication_gate_overall_eligible=publication_gate_overall_eligible,
        pr_disclosure_available=pr_disclosure_available,
        resolve_content_id=lambda candidate: dmm_connector.resolve_content_id(
            database_path, candidate
        ),
        fetch_item_response=lambda content_id: dmm_connector.fetch_item_response(
            content_id=content_id,
            env_path=env_path,
            fetcher=fetcher,
        ),
        emit_redirect=emit_redirect,
    )


__all__ = ["PIPELINE_VERSION", "run_pipeline"]
