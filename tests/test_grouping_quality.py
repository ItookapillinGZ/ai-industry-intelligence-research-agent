from __future__ import annotations

from app.events.grouping import DeterministicEventGrouper
from app.models import Event, StoredArticle


def _article(article_id: int, title: str, source: str) -> StoredArticle:
    return StoredArticle(
        id=article_id,
        title=title,
        url=f"https://example.com/{article_id}",
        source=source,
        author=None,
        published_at="2026-08-11T00:00:00+00:00",
        collected_at="2026-08-11T00:00:00+00:00",
        raw_text=title,
        summary=title,
        category="AI Product",
        importance_score=5,
        tags=["ChatGPT Work"],
        normalized_url=f"https://example.com/{article_id}",
        normalized_title=title.casefold(),
        processing_status="processed",
        llm_provider="test",
    )


def test_same_source_template_series_remain_separate() -> None:
    first = _article(1, "How data science teams use ChatGPT Work", "OpenAI News")
    second = _article(2, "How sales teams use ChatGPT Work", "OpenAI News")
    event = Event(
        id=1,
        title=first.title,
        normalized_title=first.normalized_title,
        category="AI Product",
        created_at=first.collected_at,
        updated_at=first.collected_at,
        importance_score=5,
        article_count=1,
        source_count=1,
    )
    assert DeterministicEventGrouper().similarity(second, event, [first]) == 0


def test_single_source_without_full_text_has_conservative_confidence() -> None:
    from app.research.fallback import DeterministicResearchAgent

    article = _article(1, "A standalone AI update", "Only Source")
    event = Event(
        id=1,
        title=article.title,
        normalized_title=article.normalized_title,
        category="AI Product",
        created_at=article.collected_at,
        updated_at=article.collected_at,
        importance_score=5,
        article_count=1,
        source_count=1,
    )
    assert DeterministicResearchAgent().research(event, [article]).confidence == 0.4

