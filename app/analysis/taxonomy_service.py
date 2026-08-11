from __future__ import annotations

from dataclasses import dataclass, field

from app.analysis.fallback import KeywordClassifier
from app.storage.article_repository import ArticleRepository
from app.storage.event_repository import EventRepository


@dataclass(frozen=True, slots=True)
class CategoryChange:
    article_id: int
    title: str
    old_category: str
    new_category: str


@dataclass(slots=True)
class TaxonomyStats:
    considered: int = 0
    changed: int = 0
    changes: list[CategoryChange] = field(default_factory=list)


class TaxonomyService:
    def __init__(
        self,
        article_repository: ArticleRepository,
        event_repository: EventRepository,
    ) -> None:
        self.article_repository = article_repository
        self.event_repository = event_repository
        self.classifier = KeywordClassifier()

    def reclassify(self, limit: int) -> TaxonomyStats:
        stats = TaxonomyStats()
        for article in self.article_repository.list_processed(limit):
            stats.considered += 1
            result = self.classifier.classify(article)
            if result.category != article.category:
                stats.changed += 1
                stats.changes.append(
                    CategoryChange(
                        article_id=article.id,
                        title=article.title,
                        old_category=article.category or "Other",
                        new_category=result.category,
                    )
                )
            tags = list(dict.fromkeys([*article.tags, *result.tags]))
            self.article_repository.update_classification(article.id, result, tags)
        self.event_repository.refresh_categories()
        return stats
