from __future__ import annotations

import re
from datetime import datetime, timezone
from difflib import SequenceMatcher

from app.models import Event, StoredArticle

STOP_WORDS = {
    "a", "an", "and", "as", "at", "by", "for", "from", "in", "into", "is",
    "its", "new", "of", "on", "the", "to", "with", "ai", "how", "using",
    "introducing", "launches", "launching", "released", "release",
}


def _tokens(title: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[\w]+", title.casefold(), flags=re.UNICODE)
        if token not in STOP_WORDS and len(token) > 1
    }


def _date(article: StoredArticle) -> datetime:
    value = article.published_at or article.collected_at
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.now(timezone.utc)


class DeterministicEventGrouper:
    """Conservative cross-source grouping; uncertain matches remain separate events."""

    def __init__(self, time_window_days: int = 7) -> None:
        self.time_window_days = time_window_days

    def similarity(
        self,
        article: StoredArticle,
        event: Event,
        linked_articles: list[StoredArticle],
    ) -> float:
        article_category = article.category or "Other"
        if article_category != event.category and "Other" not in {article_category, event.category}:
            return 0.0

        best = 0.0
        article_tokens = _tokens(article.title)
        if not article_tokens:
            return 0.0

        for linked in linked_articles:
            # Same-publisher template series are commonly related topics, not the same event.
            # Exact duplicates were already handled by URL/title deduplication.
            if article.source == linked.source:
                continue
            if abs((_date(article) - _date(linked)).total_seconds()) > self.time_window_days * 86400:
                continue
            if article.normalized_title == linked.normalized_title:
                return 1.0

            linked_tokens = _tokens(linked.title)
            shared = article_tokens & linked_tokens
            if len(shared) < 2:
                continue
            overlap = len(shared) / max(1, min(len(article_tokens), len(linked_tokens)))
            if overlap < 0.45:
                continue
            sequence = SequenceMatcher(
                None, article.normalized_title, linked.normalized_title
            ).ratio()
            tag_a = {tag.casefold() for tag in article.tags}
            tag_b = {tag.casefold() for tag in linked.tags}
            tag_overlap = 1.0 if tag_a & tag_b else 0.0
            score = 0.7 * overlap + 0.25 * sequence + 0.05 * tag_overlap
            if article_category != event.category:
                score -= 0.1
            best = max(best, score)
        return round(max(0.0, min(1.0, best)), 4)

