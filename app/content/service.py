from __future__ import annotations

import logging

from app.content.interfaces import ContentExtractionError, ContentExtractor
from app.models import ContentFetchStats
from app.storage.article_repository import ArticleRepository

logger = logging.getLogger(__name__)


class ContentExtractionService:
    def __init__(self, repository: ArticleRepository, extractor: ContentExtractor) -> None:
        self.repository = repository
        self.extractor = extractor

    def fetch(self, limit: int, include_failed: bool = False) -> ContentFetchStats:
        stats = ContentFetchStats()
        articles = self.repository.list_for_content_fetch(limit, include_failed=include_failed)
        for article in articles:
            if article.content_status == "fetched" and article.content:
                stats.skipped += 1
                continue
            stats.attempted += 1
            try:
                extracted = self.extractor.extract(article.url)
                self.repository.update_content_success(article.id, extracted.text)
                stats.fetched += 1
            except ContentExtractionError as exc:
                self.repository.update_content_failure(article.id, f"{exc.status}: {exc}")
                stats.failed += 1
                logger.warning("Content extraction failed for article %s: %s", article.id, exc)
            except Exception as exc:
                self.repository.update_content_failure(article.id, f"unexpected: {exc}")
                stats.failed += 1
                logger.exception("Unexpected content extraction error for article %s", article.id)
        logger.info(
            "Content fetch complete: attempted=%d fetched=%d failed=%d skipped=%d",
            stats.attempted,
            stats.fetched,
            stats.failed,
            stats.skipped,
        )
        return stats

