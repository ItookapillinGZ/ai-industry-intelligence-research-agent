from __future__ import annotations

import logging
import sqlite3

from app.collectors.base import Collector
from app.config import AppConfig
from app.models import CollectionStats
from app.services.deduplicator import Deduplicator
from app.services.normalizer import normalize_article
from app.storage.article_repository import ArticleRepository

logger = logging.getLogger(__name__)


class CollectionPipeline:
    def __init__(
        self,
        config: AppConfig,
        collector: Collector,
        repository: ArticleRepository,
        deduplicator: Deduplicator,
    ) -> None:
        self.config = config
        self.collector = collector
        self.repository = repository
        self.deduplicator = deduplicator

    def run(self) -> CollectionStats:
        stats = CollectionStats()
        if not self.config.sources:
            logger.warning("No enabled sources are configured")
            return stats

        for source in self.config.sources:
            try:
                articles = self.collector.collect(source)
            except Exception as exc:
                stats.source_errors += 1
                logger.error("Source collection failed for %s: %s", source.name, exc)
                continue

            stats.fetched += len(articles)
            for article in articles:
                try:
                    normalized = normalize_article(article)
                    duplicate = self.deduplicator.check(normalized)
                    if duplicate.is_duplicate:
                        if duplicate.reason == "url":
                            stats.duplicate_url += 1
                        else:
                            stats.duplicate_title += 1
                        logger.debug("Skipping duplicate (%s): %s", duplicate.reason, article.title)
                        continue
                    self.repository.insert(normalized)
                    stats.inserted += 1
                except sqlite3.IntegrityError as exc:
                    stats.duplicate_url += 1
                    logger.debug("Skipping concurrently inserted URL for '%s': %s", article.title, exc)
                except ValueError as exc:
                    stats.invalid += 1
                    logger.warning("Skipping invalid article '%s': %s", article.title, exc)
                except Exception:
                    stats.invalid += 1
                    logger.exception("Unexpected error while storing '%s'", article.title)

        logger.info(
            "Collection complete: fetched=%d inserted=%d duplicate_url=%d duplicate_title=%d invalid=%d source_errors=%d",
            stats.fetched,
            stats.inserted,
            stats.duplicate_url,
            stats.duplicate_title,
            stats.invalid,
            stats.source_errors,
        )
        return stats

