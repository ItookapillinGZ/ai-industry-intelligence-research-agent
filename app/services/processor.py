from __future__ import annotations

import logging

from app.analysis.interfaces import AnalysisComponents
from app.storage.article_repository import ArticleRepository

logger = logging.getLogger(__name__)


class ArticleProcessor:
    def __init__(self, repository: ArticleRepository, components: AnalysisComponents) -> None:
        self.repository = repository
        self.components = components

    def process(self, limit: int, include_failed: bool = False) -> tuple[int, int]:
        articles = self.repository.list_pending(limit, include_failed=include_failed)
        processed = 0
        failed = 0
        for article in articles:
            try:
                classification = self.components.classifier.classify(article)
                score = self.components.scorer.score(article, classification)
                summary = self.components.summarizer.summarize(article)
                tags = list(dict.fromkeys([*article.tags, *classification.tags]))
                self.repository.update_analysis(
                    article.id,
                    classification,
                    score,
                    summary,
                    tags,
                    self.components.provider_name,
                )
                processed += 1
            except Exception:
                logger.exception("Failed to process article %s (%s)", article.id, article.title)
                self.repository.mark_failed(article.id)
                failed += 1
        logger.info("Processing complete: %d processed, %d failed", processed, failed)
        return processed, failed

