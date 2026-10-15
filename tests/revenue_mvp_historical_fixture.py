"""Test-only exact historical baseline fixture; never a production authority.

Recover old test bytes only from pinned baseline/display/copy identities.
Unknown/currently changed artifacts cannot become historical proof.
No receipt, approval, timestamp, or production file is altered.
"""
from hashlib import sha256
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import revenue_mvp_price_display_transition as display
import revenue_mvp_price_filter_copy_candidate as price_copy


def price_display_artifact(artifact_bytes):
    """Pinned pre-copy fixture only, not current display or eligibility evidence."""
    canonical = display.canonical(artifact_bytes)
    if sha256(canonical).hexdigest() == price_copy.CANDIDATE_SHA256:
        canonical = display.canonical(price_copy.recover_source(canonical))
    if sha256(canonical).hexdigest() != display.CANDIDATE:
        raise ValueError('UNKNOWN_ARTIFACT_NOT_PRICE_DISPLAY_FIXTURE')
    return canonical


def historical_artifact(artifact_bytes):
    canonical=display.canonical(artifact_bytes)
    digest=sha256(canonical).hexdigest()
    if digest == price_copy.CANDIDATE_SHA256:
        canonical = price_display_artifact(canonical)
        digest = sha256(canonical).hexdigest()
    if digest == display.BASELINE:
        return canonical
    if digest != display.CANDIDATE:
        raise ValueError('UNKNOWN_ARTIFACT_NOT_HISTORICAL_FIXTURE')
    exact=(chr(0x5186)+'</p>').encode()
    lower=(chr(0x5186)+chr(0x301c)+'</p>').encode()
    if canonical.count(lower)!=100:
        raise ValueError('DISPLAY_FIXTURE_DELTA_INVALID')
    baseline=canonical.replace(lower,exact)
    if sha256(baseline).hexdigest()!=display.BASELINE:
        raise ValueError('HISTORICAL_FIXTURE_HASH_INVALID')
    return baseline


def historical_state_fixture():
    """Explicit test context for old approval, never current LIVE evidence."""
    import json
    import revenue_mvp_current_state as state
    artifact=historical_artifact(state.ARTIFACT_PATH.read_bytes())
    receipt=json.loads(state.RECEIPT_PATH.read_text(encoding='utf-8'))
    live=json.loads(state.REFRESHED_PRODUCT_CARD_LIVE_EVIDENCE_PATH.read_text(encoding='utf-8'))
    return state.assess(receipt,artifact,None,None,None,live)
