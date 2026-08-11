from __future__ import annotations

from app.models import ArticleInput
from app.services.normalizer import normalize_article
from app.storage.article_repository import ArticleRepository


def test_dedup_caches_include_articles_inserted_after_snapshot(
    repository: ArticleRepository,
) -> None:
    assert not repository.exists_by_url("https://example.com/new")
    assert repository.recent_titles(30) == []

    normalized = normalize_article(
        ArticleInput(
            title="New article after cache initialization",
            url="https://example.com/new",
            source="Test",
        )
    )
    article_id = repository.insert(normalized)

    assert repository.exists_by_url("https://example.com/new")
    assert repository.recent_titles(30) == [
        (article_id, normalized.article.title, normalized.normalized_title)
    ]
