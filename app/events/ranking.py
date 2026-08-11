from __future__ import annotations

from datetime import datetime, timezone

from app.models import Event, StoredArticle


def _age_days(article: StoredArticle) -> float:
    value = article.published_at or article.collected_at
    try:
        date = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if not date.tzinfo:
            date = date.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - date).total_seconds() / 86400)
    except ValueError:
        return 30.0


class DeterministicEventScorer:
    def score(self, event: Event, articles: list[StoredArticle]) -> float:
        if not articles:
            return 0.0
        base = max(float(article.importance_score or 0) for article in articles)
        sources = len({article.source for article in articles})
        diversity = min(1.2, max(0, sources - 1) * 0.6)
        independent_corroboration = min(0.6, max(0, sources - 1) * 0.2)
        newest_age = min(_age_days(article) for article in articles)
        recency = 0.6 if newest_age <= 2 else 0.4 if newest_age <= 7 else 0.2 if newest_age <= 30 else 0
        category_bonus = 0.2 if event.category != "Other" else 0.0
        return round(
            min(10.0, base + diversity + independent_corroboration + recency + category_bonus),
            2,
        )


# Phase 2.5 keeps the import path stable while using the auditable scorer.
from app.events.importance import AuditableEventScorer as DeterministicEventScorer
