"""Test-only exact historical baseline fixture; never a production authority.

Recover the old bytes only from either pinned baseline or pinned display-only
candidate. Unknown/currently changed artifacts cannot become historical proof.
No receipt, approval, timestamp, or production file is altered.
"""
from hashlib import sha256
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import revenue_mvp_price_display_transition as display


def historical_artifact(artifact_bytes):
    canonical=display.canonical(artifact_bytes)
    digest=sha256(canonical).hexdigest()
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
