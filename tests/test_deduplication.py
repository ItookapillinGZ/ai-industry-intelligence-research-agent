from __future__ import annotations

from app.models import ArticleInput
from app.services.deduplicator import Deduplicator
from app.services.normalizer import normalize_article
from app.storage.article_repository import ArticleRepository


def _article(title: str, url: str):
    return normalize_article(ArticleInput(title=title, url=url, source="Test Source"))


def test_deduplicates_tracking_variants_by_url(repository: ArticleRepository) -> None:
    repository.insert(_article("First story", "https://example.com/story?utm_source=rss"))
    result = Deduplicator(repository).check(
        _article("Different title", "https://example.com/story#comments")
    )
    assert result.is_duplicate
    assert result.reason == "url"


def test_deduplicates_similar_titles(repository: ArticleRepository) -> None:
    repository.insert(
        _article(
            "OpenAI launches a new reasoning model for developers",
            "https://first.example/story",
        )
    )
    result = Deduplicator(repository, title_similarity_threshold=0.85).check(
        _article(
            "OpenAI launches new reasoning model for developers",
            "https://second.example/article",
        )
    )
    assert result.is_duplicate
    assert result.reason == "title"
    assert result.similarity is not None and result.similarity >= 0.85


def test_distinct_titles_are_not_duplicates(repository: ArticleRepository) -> None:
    repository.insert(_article("New video generation model released", "https://a.example/1"))
    result = Deduplicator(repository).check(
        _article("AI startup raises Series B funding", "https://b.example/2")
    )
    assert not result.is_duplicate

