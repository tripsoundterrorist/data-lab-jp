"""Fail-closed reconciliation for the live reduced product-card surface.

The command prints only opaque public IDs and aggregate counts. Provider content
IDs and image URLs remain in memory for trusted callers and are never logged.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape, unescape
from html.parser import HTMLParser
import json
from pathlib import Path
import sqlite3
from typing import Any

from revenue_mvp_lifecycle_receipt import public_item_id


@dataclass(frozen=True)
class LiveCard:
    title: str
    price: int
    observed_at: str


@dataclass(frozen=True)
class ReconciledCard:
    public_id: str
    content_id: str
    title: str
    price: int
    observed_at: str
    image_url: str


class _CardParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.cards: list[LiveCard] = []
        self._in_card = False
        self._field: str | None = None
        self._values: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        classes = set((values.get("class") or "").split())
        if tag == "article" and "item" in classes:
            if self._in_card:
                raise ValueError("NESTED_CARD")
            self._in_card = True
            self._values = {}
        elif self._in_card and tag == "h2":
            self._field = "title"
        elif self._in_card and tag == "p" and "price" in classes:
            self._field = "price"
        elif self._in_card and tag == "time":
            self._field = "observed_at"

    def handle_endtag(self, tag: str) -> None:
        if self._in_card and tag in {"h2", "p", "time"}:
            self._field = None
        if tag == "article" and self._in_card:
            if set(self._values) != {"title", "price", "observed_at"}:
                raise ValueError("CARD_FIELDS_INVALID")
            price_text = self._values["price"].removesuffix("円").replace(",", "")
            if not price_text.isdigit():
                raise ValueError("CARD_PRICE_INVALID")
            self.cards.append(LiveCard(
                unescape(self._values["title"]).strip(),
                int(price_text),
                self._values["observed_at"].strip(),
            ))
            self._in_card = False
            self._values = {}

    def handle_data(self, data: str) -> None:
        if self._in_card and self._field:
            self._values[self._field] = self._values.get(self._field, "") + data


def _valid_image_url(value: Any) -> bool:
    if type(value) is not str or not value.startswith("https://pics.dmm.co.jp/"):
        return False
    return not any(character.isspace() for character in value)


def _utc_timestamp(value: Any) -> str:
    if type(value) is not str:
        raise ValueError("OBSERVATION_TIMESTAMP_INVALID")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("OBSERVATION_TIMESTAMP_INVALID")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def reconcile(source: bytes, database: Path) -> list[ReconciledCard]:
    parser = _CardParser()
    parser.feed(source.decode("utf-8"))
    if not parser.cards:
        raise ValueError("LIVE_CARDS_REQUIRED")

    connection = sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only = ON")
        rows = connection.execute("""
            SELECT i.site, i.service, i.floor, i.content_id, i.image_url_large,
                   s.price_min, s.observed_at, t.title
            FROM item_snapshots AS s
            JOIN items AS i ON i.id = s.item_id
            JOIN item_snapshot_titles AS t ON t.snapshot_id = s.id
            WHERE t.observed_at = s.observed_at
        """).fetchall()
    finally:
        connection.close()

    by_key: dict[tuple[str, int, str], list[sqlite3.Row]] = {}
    for row in rows:
        if row["price_min"] is None:
            continue
        by_key.setdefault(
            (row["title"], row["price_min"], _utc_timestamp(row["observed_at"])), [],
        ).append(row)

    reconciled: list[ReconciledCard] = []
    seen: set[str] = set()
    missing = 0
    ambiguous = 0
    for card in parser.cards:
        matches = by_key.get((card.title, card.price, card.observed_at), [])
        if len(matches) != 1:
            missing += len(matches) == 0
            ambiguous += len(matches) > 1
            continue
        row = matches[0]
        values = (row["site"], row["service"], row["floor"], row["content_id"])
        if not all(type(value) is str and value for value in values):
            raise ValueError("SOURCE_IDENTITY_INVALID")
        opaque_id = public_item_id(*values)
        if opaque_id in seen or not _valid_image_url(row["image_url_large"]):
            raise ValueError("PRODUCT_CARD_ASSET_INVALID")
        seen.add(opaque_id)
        reconciled.append(ReconciledCard(
            opaque_id, row["content_id"], card.title, card.price,
            card.observed_at, row["image_url_large"],
        ))
    if missing or ambiguous or len(reconciled) != len(parser.cards):
        raise ValueError(
            f"LIVE_CARD_BINDING_NOT_UNIQUE:missing={missing}:ambiguous={ambiguous}"
        )
    return reconciled


def enrich(source: bytes, database: Path, cta_public_ids: frozenset[str]) -> bytes:
    cards = reconcile(source, database)
    known = {card.public_id for card in cards}
    if not cta_public_ids or not cta_public_ids <= known:
        raise ValueError("CTA_SCOPE_INVALID")
    text = source.decode("utf-8")
    for card in cards:
        title = escape(card.title)
        prefix = (
            '<article class="item"><h2>' + title + '</h2>'
            f'<p class="price">{card.price:,}円</p><time>{escape(card.observed_at)}</time>'
        )
        if text.count(prefix) != 1:
            raise ValueError("LIVE_CARD_HTML_NOT_EXACT")
        start = text.index(prefix)
        end = text.index("</article>", start) + len("</article>")
        article = text[start:end]
        image = (
            '<div class="card-image-wrap"><img class="card-image" src="'
            + escape(card.image_url, quote=True) + '" alt="' + title
            + '" loading="lazy" decoding="async"></div>'
        )
        article = article.replace('<article class="item">', '<article class="item">' + image, 1)
        has_cta = 'class="affiliate-cta-block"' in article
        selected = card.public_id in cta_public_ids
        if selected and not has_cta:
            cta = (
                '<aside class="affiliate-cta-block" aria-label="広告リンク">'
                '<p class="affiliate-cta-disclosure">【PR】FANZAで確認</p>'
                '<a class="affiliate-cta-link" href="/go/' + card.public_id
                + '" target="_blank" rel="noopener noreferrer sponsored">'
                'FANZAの商品ページを確認（外部サイト）</a></aside>'
            )
            article = article.replace("</article>", cta + "</article>", 1)
        elif selected and f'href="/go/{card.public_id}"' not in article:
            raise ValueError("EXISTING_CTA_BINDING_MISMATCH")
        elif not selected and has_cta:
            raise ValueError("UNSELECTED_CTA_PRESENT")
        text = text[:start] + article + text[end:]
    if text.count('class="card-image"') != len(cards):
        raise ValueError("IMAGE_COUNT_MISMATCH")
    if text.count('class="affiliate-cta-block"') != len(cta_public_ids):
        raise ValueError("CTA_COUNT_MISMATCH")
    if "affiliateURL" in text or "DMM_AFFILIATE_ID" in text:
        raise ValueError("PRIVATE_VALUE_EXPOSURE_BLOCKED")
    return text.encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--cta-public-id", action="append", default=[])
    args = parser.parse_args()
    try:
        source = args.source.read_bytes()
        cards = reconcile(source, args.db)
        if args.output:
            payload = enrich(source, args.db, frozenset(args.cta_public_id))
            args.output.write_bytes(payload)
    except ValueError as error:
        print(json.dumps({"status": "BLOCKED", "reason": str(error)}, sort_keys=True))
        return 1
    except (OSError, UnicodeError, sqlite3.Error):
        print(json.dumps({"status": "BLOCKED", "reason": "SOURCE_READ_FAILED"}, sort_keys=True))
        return 1
    print(json.dumps({
        "status": "READY",
        "card_count": len(cards),
        "image_count": sum(bool(card.image_url) for card in cards),
        "output_written": args.output is not None,
        "public_ids": [card.public_id for card in cards[:10]],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
