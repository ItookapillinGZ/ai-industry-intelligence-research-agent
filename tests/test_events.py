from __future__ import annotations

from datetime import datetime, timezone

from app.events.grouping import DeterministicEventGrouper
from app.events.ranking import DeterministicEventScorer
from app.events.service import EventGroupingService, EventRankingService
from app.models import ArticleInput, ClassificationResult
from app.services.normalizer import normalize_article
from app.storage.article_repository import ArticleRepository
from app.storage.event_repository import EventRepository


def _processed(
    repository: ArticleRepository,
    title: str,
    url: str,
    source: str,
    category: str = "LLM",
) -> int:
    article_id = repository.insert(
        normalize_article(
            ArticleInput(
                title=title,
                url=url,
                source=source,
                published_at=datetime.now(timezone.utc).isoformat(),
                raw_text=title,
            )
        )
    )
    repository.update_analysis(
        article_id,
        ClassificationResult(category=category),
        7.0,
        title,
        [],
        "test",
    )
    return article_id


def test_same_event_groups_cross_source_articles(repository: ArticleRepository) -> None:
    _processed(repository, "OpenAI launches GPT-5 reasoning model", "https://a.test/1", "Source A")
    _processed(
        repository,
        "GPT-5 reasoning model launched by OpenAI",
        "https://b.test/2",
        "Source B",
    )
    event_repository = EventRepository(repository.database)
    service = EventGroupingService(
        event_repository,
        DeterministicEventGrouper(time_window_days=7),
        similarity_threshold=0.62,
    )

    stats = service.group(limit=10)

    assert stats.events_created == 1
    event = event_repository.list_events()[0]
    assert event.article_count == 2
    assert event.source_count == 2
    ranked = EventRankingService(event_repository, DeterministicEventScorer()).rank(1)
    assert ranked[0].importance_score > 7.0


def test_distinct_events_are_not_forced_together(repository: ArticleRepository) -> None:
    _processed(repository, "OpenAI launches GPT-5 reasoning model", "https://a.test/model", "A")
    _processed(repository, "OpenAI announces new funding round", "https://b.test/funding", "B")
    event_repository = EventRepository(repository.database)
    stats = EventGroupingService(
        event_repository,
        DeterministicEventGrouper(),
        similarity_threshold=0.62,
    ).group(limit=10)

    assert stats.events_created == 2
    assert event_repository.count() == 2

