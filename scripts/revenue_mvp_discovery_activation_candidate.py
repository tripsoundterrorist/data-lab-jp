"""Build a review-only discovery-controls candidate from the current live source.

The transformation is deliberately narrow: it adds the reviewed local script and
controls around the existing grid while preserving every product card byte for
byte.  It cannot write inside the repository or activate production.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile


ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.1-candidate"
HEAD_MARKER = '<script src="/analytics-consent.js" defer></script><title>'
HEAD_REPLACEMENT = (
    '<script src="/analytics-consent.js" defer></script>'
    '<script src="discovery.js" defer></script><title>'
)
MAIN_PATTERN = re.compile(
    r'(<main id="main-content">)'
    r'(<p id="result-count" role="status" aria-live="polite">([1-9][0-9]*)件</p>)'
    r'(<p id="page-status" aria-live="polite">1 / 1</p>)'
    r'(<section class="item-grid">)'
)
CARD_PATTERN = re.compile(r'<article class="item">.*?</article>', re.DOTALL)
GO_PATTERN = re.compile(r'href="/go/(itm_[a-f0-9]{24})"')
CONTROLS = (
    '<section class="controls panel" aria-label="商品を絞り込む">'
    '<label>商品名で検索<input id="item-search" type="search" autocomplete="off" placeholder="商品名を入力"></label>'
    '<label>価格帯<select id="price-filter"><option value="all">すべて</option>'
    '<option value="under-1000">1,000円未満</option><option value="1000-1999">1,000〜1,999円</option>'
    '<option value="2000-2999">2,000〜2,999円</option><option value="3000-plus">3,000円以上</option>'
    '</select></label><label>並び替え<select id="item-sort"><option value="original">掲載順</option>'
    '<option value="price-asc">価格が安い順</option><option value="price-desc">価格が高い順</option>'
    '<option value="observed-desc">確認日時が新しい順</option><option value="observed-asc">確認日時が古い順</option>'
    '</select></label></section><div class="results-head">'
)


class CandidateFailure(ValueError):
    pass


@dataclass(frozen=True)
class CandidateReceipt:
    version: str
    status: str
    source_sha256: str
    candidate_sha256: str
    item_count: int
    image_count: int
    cta_count: int
    card_bytes_preserved: bool
    go_routes_preserved: bool
    production_write_performed: bool = False
    activation_allowed: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def build(source: bytes, *, expected_sha256: str, expected_item_count: int) -> tuple[bytes, CandidateReceipt]:
    if len(expected_sha256) != 64 or _sha256(source) != expected_sha256:
        raise CandidateFailure("SOURCE_HASH_MISMATCH")
    if type(expected_item_count) is not int or expected_item_count <= 0:
        raise CandidateFailure("ITEM_COUNT_INVALID")
    try:
        text = source.decode("utf-8")
    except UnicodeDecodeError as error:
        raise CandidateFailure("SOURCE_ENCODING_INVALID") from error
    if "discovery.js" in text or 'id="item-search"' in text:
        raise CandidateFailure("DISCOVERY_CONTROLS_ALREADY_PRESENT")
    if text.count(HEAD_MARKER) != 1:
        raise CandidateFailure("HEAD_INSERTION_POINT_INVALID")
    cards = CARD_PATTERN.findall(text)
    go_routes = GO_PATTERN.findall(text)
    image_count = text.count('class="card-image"')
    cta_count = text.count('class="affiliate-cta-block"')
    if not (len(cards) == len(go_routes) == image_count == cta_count == expected_item_count):
        raise CandidateFailure("LIVE_CARD_SCOPE_INVALID")
    if len(set(go_routes)) != expected_item_count:
        raise CandidateFailure("GO_ROUTE_SCOPE_INVALID")
    match = MAIN_PATTERN.search(text)
    if match is None or int(match.group(3)) != expected_item_count:
        raise CandidateFailure("MAIN_INSERTION_POINT_INVALID")
    text = text.replace(HEAD_MARKER, HEAD_REPLACEMENT, 1)
    replacement = (
        match.group(1) + CONTROLS + match.group(2)
        + '<p id="page-status" aria-live="polite">全商品を表示</p></div>'
        + match.group(5)
    )
    text = MAIN_PATTERN.sub(lambda _match: replacement, text, count=1)
    candidate = text.encode("utf-8")
    candidate_cards = CARD_PATTERN.findall(text)
    candidate_routes = GO_PATTERN.findall(text)
    if candidate_cards != cards:
        raise CandidateFailure("CARD_BYTES_CHANGED")
    if candidate_routes != go_routes:
        raise CandidateFailure("GO_ROUTES_CHANGED")
    if candidate.count(b'<script src="discovery.js" defer></script>') != 1:
        raise CandidateFailure("DISCOVERY_SCRIPT_INVALID")
    return candidate, CandidateReceipt(
        VERSION, "READY_FOR_EXACT_REVIEW", expected_sha256, _sha256(candidate),
        expected_item_count, image_count, cta_count, True, True,
    )


def write_candidate(path: Path, payload: bytes) -> None:
    target = path.resolve()
    try:
        target.relative_to(ROOT.resolve())
    except ValueError:
        pass
    else:
        raise CandidateFailure("OUTPUT_MUST_BE_OUTSIDE_REPOSITORY")
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix="discovery-candidate-", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
        os.replace(temporary, target)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--expected-item-count", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload, receipt = build(
        args.source.read_bytes(), expected_sha256=args.expected_sha256,
        expected_item_count=args.expected_item_count,
    )
    write_candidate(args.output, payload)
    print(json.dumps(receipt.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["CandidateFailure", "CandidateReceipt", "build", "write_candidate"]
