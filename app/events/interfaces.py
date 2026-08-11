from __future__ import annotations

from typing import Protocol

from app.models import Event, StoredArticle


class EventGrouper(Protocol):
    def similarity(
        self,
        article: StoredArticle,
        event: Event,
        linked_articles: list[StoredArticle],
    ) -> float: ...


class EventScorer(Protocol):
    def score(self, event: Event, articles: list[StoredArticle]) -> float: ...

