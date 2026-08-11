from __future__ import annotations

import html
import logging
from datetime import datetime, timezone
from html.parser import HTMLParser
from time import struct_time
from urllib.request import Request, urlopen

import feedparser

from app.config import RSSSourceConfig
from app.models import ArticleInput

logger = logging.getLogger(__name__)


class RSSCollectionError(RuntimeError):
    """Raised when an RSS source cannot be collected."""


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self.parts.append(text)


def _html_to_text(value: str) -> str:
    parser = _TextExtractor()
    try:
        parser.feed(html.unescape(value or ""))
        return " ".join(parser.parts)
    except Exception:
        return html.unescape(value or "").strip()


def _published_iso(value: struct_time | None) -> str | None:
    if not value:
        return None
    return datetime(*value[:6], tzinfo=timezone.utc).isoformat()


class RSSCollector:
    def __init__(self, timeout_seconds: int = 20) -> None:
        self.timeout_seconds = timeout_seconds

    def collect(self, source: RSSSourceConfig) -> list[ArticleInput]:
        request = Request(
            source.url,
            headers={
                "User-Agent": "AI-Industry-Intelligence-Research-Agent/0.1 (+RSS research workflow)",
                "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = response.read()
        except Exception as exc:
            raise RSSCollectionError(f"Could not fetch {source.name}: {exc}") from exc

        feed = feedparser.parse(payload)
        if feed.bozo and not feed.entries:
            raise RSSCollectionError(
                f"Could not parse {source.name}: {getattr(feed, 'bozo_exception', 'unknown error')}"
            )

        articles: list[ArticleInput] = []
        entries = feed.entries[: source.max_items]
        for entry in entries:
            title = str(entry.get("title", "")).strip()
            url = str(entry.get("link", "")).strip()
            if not title or not url:
                logger.warning("Skipping RSS entry without title or URL from %s", source.name)
                continue

            content_blocks = entry.get("content") or []
            raw_html = ""
            if content_blocks and isinstance(content_blocks, list):
                raw_html = str(content_blocks[0].get("value", ""))
            if not raw_html:
                raw_html = str(entry.get("summary", entry.get("description", "")))

            entry_tags = [
                str(tag.get("term", "")).strip()
                for tag in entry.get("tags", [])
                if tag.get("term")
            ]
            articles.append(
                ArticleInput(
                    title=_html_to_text(title),
                    url=url,
                    source=source.name,
                    author=str(entry.get("author", "")).strip() or None,
                    published_at=_published_iso(
                        entry.get("published_parsed") or entry.get("updated_parsed")
                    ),
                    raw_text=_html_to_text(raw_html),
                    tags=list(dict.fromkeys([*source.tags, *entry_tags])),
                )
            )

        logger.info(
            "Fetched %d entries from %s (%d available, limit=%d)",
            len(articles),
            source.name,
            len(feed.entries),
            source.max_items,
        )
        return articles

