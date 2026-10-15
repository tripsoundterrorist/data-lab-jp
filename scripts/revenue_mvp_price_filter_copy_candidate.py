"""Pure, exact-source copy candidate. No I/O, activation, or inherited authority."""
from dataclasses import dataclass
from hashlib import sha256
import re

SOURCE_SHA256 = "07083ce28e1095ce75ea89fa453ecb8c3e6fc6626e679397ca046d167d59d88b"
CANDIDATE_SHA256 = "fcdb686092f35840cf5a9aacf6a01ac27ed269045ec4caabf5ef05809c57f39d"
NOTICE = (
    '<p class="notice" id="price-lower-bound-note">'
    '「円〜」は確認時点の最低価格です。購入金額を保証するものではありません。'
    '最新の価格・条件は公式ページでご確認ください。</p>'
)
REPLACEMENTS = (
    ('<label>価格帯<select id="price-filter">',
     '<label>表示価格の下限で絞り込む<select id="price-filter">'),
    ('<option value="price-asc">価格が安い順</option>',
     '<option value="price-asc">表示価格の下限が低い順</option>'),
    ('<option value="price-desc">価格が高い順</option>',
     '<option value="price-desc">表示価格の下限が高い順</option>'),
    ('</select></label></section><div class="results-head">',
     '</select></label></section>' + NOTICE + '<div class="results-head">'),
)
CARD_PATTERN = re.compile(r'<article class="item">.*?</article>', re.DOTALL)


@dataclass(frozen=True)
class CopyCandidateReceipt:
    source_sha256: str
    candidate_sha256: str
    item_count: int
    card_bytes_preserved: bool
    status: str = "COPY_CANDIDATE_REQUIRES_SEPARATE_REVIEW"
    publication_allowed: bool = False
    gate_mutation_allowed: bool = False
    current_eligibility_verified: bool = False
    live_display_verified: bool = False
    production_write_performed: bool = False
    database_write_performed: bool = False


def _canonical(payload: bytes) -> bytes:
    return payload.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def build(source: bytes) -> tuple[bytes, CopyCandidateReceipt]:
    """Return candidate bytes only; never write or update monitoring/Gate evidence."""
    if type(source) is not bytes or len(source) > 1024 * 1024:
        raise ValueError("COPY_SOURCE_INVALID")
    try:
        digest = sha256(_canonical(source)).hexdigest()
        text = source.decode("utf-8")
    except UnicodeError as error:
        raise ValueError("COPY_SOURCE_INVALID") from error
    if digest != SOURCE_SHA256:
        raise ValueError("COPY_SOURCE_BINDING_INVALID")
    cards = CARD_PATTERN.findall(text)
    if len(cards) != 100 or text.count('円〜</p>') != 100:
        raise ValueError("COPY_CARD_SCOPE_INVALID")
    original = text
    for old, new in REPLACEMENTS:
        if text.count(old) != 1 or new in text:
            raise ValueError("COPY_INSERTION_POINT_INVALID")
        text = text.replace(old, new, 1)
    if CARD_PATTERN.findall(text) != cards:
        raise ValueError("COPY_CARD_BYTES_CHANGED")
    restored = text
    for old, new in reversed(REPLACEMENTS):
        if restored.count(new) != 1:
            raise ValueError("COPY_DELTA_INVALID")
        restored = restored.replace(new, old, 1)
    if restored != original:
        raise ValueError("COPY_DELTA_INVALID")
    candidate = text.encode("utf-8")
    return candidate, CopyCandidateReceipt(
        digest, sha256(_canonical(candidate)).hexdigest(), len(cards), True,
    )


def recover_source(candidate: bytes) -> bytes:
    """Recognize only the exact copy delta; recovery is not LIVE evidence."""
    if type(candidate) is not bytes or len(candidate) > 1024 * 1024:
        raise ValueError("COPY_CANDIDATE_INVALID")
    try:
        if sha256(_canonical(candidate)).hexdigest() != CANDIDATE_SHA256:
            raise ValueError("COPY_CANDIDATE_BINDING_INVALID")
        text = candidate.decode("utf-8")
        for old, new in reversed(REPLACEMENTS):
            if text.count(new) != 1:
                raise ValueError("COPY_DELTA_INVALID")
            text = text.replace(new, old, 1)
        source = text.encode("utf-8")
        rebuilt, _ = build(source)
        if rebuilt != candidate:
            raise ValueError("COPY_REBUILD_MISMATCH")
        return source
    except UnicodeError as error:
        raise ValueError("COPY_CANDIDATE_INVALID") from error
