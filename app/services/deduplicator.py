from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

from app.models import NormalizedArticle
from app.storage.article_repository import ArticleRepository


@dataclass(frozen=True, slots=True)
class DuplicateResult:
    is_duplicate: bool
    reason: str | None = None
    matched_article_id: int | None = None
    similarity: float | None = None


class Deduplicator:
    def __init__(
        self,
        repository: ArticleRepository,
        title_similarity_threshold: float = 0.92,
        lookback_days: int = 30,
    ) -> None:
        self.repository = repository
        self.title_similarity_threshold = title_similarity_threshold
        self.lookback_days = lookback_days

    def check(self, article: NormalizedArticle) -> DuplicateResult:
        if self.repository.exists_by_url(article.normalized_url):
            return DuplicateResult(is_duplicate=True, reason="url")

        candidate = article.normalized_title
        if not candidate:
            return DuplicateResult(is_duplicate=False)

        for article_id, _title, normalized_title in self.repository.recent_titles(self.lookback_days):
            length_ratio = min(len(candidate), len(normalized_title)) / max(
                len(candidate), len(normalized_title), 1
            )
            if length_ratio < self.title_similarity_threshold * 0.75:
                continue
            similarity = SequenceMatcher(None, candidate, normalized_title).ratio()
            if similarity >= self.title_similarity_threshold:
                return DuplicateResult(
                    is_duplicate=True,
                    reason="title",
                    matched_article_id=article_id,
                    similarity=similarity,
                )
        return DuplicateResult(is_duplicate=False)

