from __future__ import annotations

import re

from app.models import Event, StoredArticle

QUERY_STOP_WORDS = {
    "a", "an", "and", "as", "at", "for", "from", "how", "in", "into", "is",
    "of", "on", "the", "to", "with", "we", "our", "new", "launching", "introducing",
}


def _keywords(value: str, limit: int = 9) -> list[str]:
    items = [
        token
        for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9.+-]*", value)
        if token.casefold() not in QUERY_STOP_WORDS and len(token) > 1
    ]
    return list(dict.fromkeys(items))[:limit]


def build_evidence_queries(event: Event, articles: list[StoredArticle]) -> list[str]:
    title = " ".join(_keywords(event.title, 12))
    entities: list[str] = []
    for article in articles:
        entities.extend(tag for tag in article.tags if 1 < len(tag) <= 40)
        entities.extend(
            token
            for token in re.findall(r"\b[A-Z][A-Za-z0-9.+-]{2,}\b", article.title)
            if token.casefold() not in QUERY_STOP_WORDS
        )
    entities = list(dict.fromkeys(entities))[:4]
    focused = " ".join([*entities[:2], *_keywords(event.title, 6)])
    queries = [
        f'"{event.title}"',
        f"{focused} official announcement",
        f"{title} independent analysis",
    ]
    return [query.strip() for query in dict.fromkeys(queries) if query.strip()]
