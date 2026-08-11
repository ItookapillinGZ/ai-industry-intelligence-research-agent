from __future__ import annotations

import logging
from dataclasses import dataclass

from app.research.interfaces import ResearchAgent
from app.storage.event_repository import EventRepository
from app.storage.research_repository import ResearchRepository

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ResearchStats:
    considered: int = 0
    generated: int = 0
    skipped: int = 0
    failed: int = 0


class ResearchService:
    def __init__(
        self,
        event_repository: EventRepository,
        research_repository: ResearchRepository,
        agent: ResearchAgent,
    ) -> None:
        self.event_repository = event_repository
        self.research_repository = research_repository
        self.agent = agent

    def research_top_events(self, top_k: int, force: bool = False) -> ResearchStats:
        stats = ResearchStats()
        for event in self.event_repository.list_events(limit=top_k):
            stats.considered += 1
            if self.research_repository.get_by_event(event.id) and not force:
                stats.skipped += 1
                continue
            try:
                articles = self.event_repository.list_articles(event.id)
                brief = self.agent.research(event, articles)
                self.research_repository.save(brief)
                stats.generated += 1
            except Exception:
                stats.failed += 1
                logger.exception("Research failed for event %s", event.id)
        logger.info(
            "Research complete: considered=%d generated=%d skipped=%d failed=%d",
            stats.considered,
            stats.generated,
            stats.skipped,
            stats.failed,
        )
        return stats

