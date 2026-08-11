from __future__ import annotations

import logging

from app.events.interfaces import EventGrouper, EventScorer
from app.models import Event, EventGroupingStats, StoredArticle
from app.storage.event_repository import EventRepository

logger = logging.getLogger(__name__)


class EventGroupingService:
    def __init__(
        self,
        repository: EventRepository,
        grouper: EventGrouper,
        similarity_threshold: float,
    ) -> None:
        self.repository = repository
        self.grouper = grouper
        self.similarity_threshold = similarity_threshold

    def group(self, limit: int) -> EventGroupingStats:
        stats = EventGroupingStats()
        events = self.repository.list_events()
        linked: dict[int, list[StoredArticle]] = {
            event.id: self.repository.list_articles(event.id) for event in events
        }

        for article in self.repository.list_ungrouped_articles(limit):
            stats.articles_considered += 1
            best_event: Event | None = None
            best_score = 0.0
            for event in events:
                score = self.grouper.similarity(article, event, linked[event.id])
                if score > best_score:
                    best_score = score
                    best_event = event

            if best_event is None or best_score < self.similarity_threshold:
                best_event = self.repository.create_event(article)
                events.append(best_event)
                linked[best_event.id] = []
                best_score = 1.0
                stats.events_created += 1

            self.repository.link_article(best_event.id, article.id, best_score)
            linked[best_event.id].append(article)
            updated = self.repository.update_metrics(best_event.id)
            events[events.index(best_event)] = updated
            stats.articles_linked += 1

        logger.info(
            "Event grouping complete: considered=%d created=%d linked=%d",
            stats.articles_considered,
            stats.events_created,
            stats.articles_linked,
        )
        return stats


class EventRankingService:
    def __init__(self, repository: EventRepository, scorer: EventScorer) -> None:
        self.repository = repository
        self.scorer = scorer

    def rank(self, top_k: int) -> list[Event]:
        for event in self.repository.list_events():
            articles = self.repository.list_articles(event.id)
            self.repository.update_importance(event.id, self.scorer.score(event, articles))
        return self.repository.list_events(limit=top_k)

