from __future__ import annotations

from pathlib import Path

from app.config import AppConfig, RSSSourceConfig
from app.models import ArticleInput
from app.services.deduplicator import Deduplicator
from app.services.pipeline import CollectionPipeline
from app.storage.article_repository import ArticleRepository


class FakeCollector:
    def collect(self, source: RSSSourceConfig) -> list[ArticleInput]:
        return [
            ArticleInput(
                title="A new agent framework",
                url="https://example.com/agent?utm_medium=rss",
                source=source.name,
                raw_text="A new agent framework was released.",
            ),
            ArticleInput(
                title="A new agent framework",
                url="https://example.com/agent",
                source=source.name,
                raw_text="Duplicate entry.",
            ),
        ]


def test_collection_pipeline_stores_and_deduplicates(
    repository: ArticleRepository, tmp_path: Path
) -> None:
    config = AppConfig(
        database_path=tmp_path / "test.db",
        reports_dir=tmp_path / "reports",
        logs_dir=tmp_path / "logs",
        sources=(RSSSourceConfig(name="Fake", url="https://example.com/feed"),),
    )
    pipeline = CollectionPipeline(
        config,
        FakeCollector(),
        repository,
        Deduplicator(repository),
    )
    stats = pipeline.run()
    assert stats.fetched == 2
    assert stats.inserted == 1
    assert stats.duplicate_url == 1
    assert repository.count() == 1

