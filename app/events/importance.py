from __future__ import annotations

from datetime import datetime, timezone

from app.evidence.source_types import classify_source_type
from app.models import Event, ImportanceBreakdown, StoredArticle


def _age_days(article: StoredArticle) -> float:
    value = article.published_at or article.collected_at
    try:
        date = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if not date.tzinfo:
            date = date.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - date).total_seconds() / 86400)
    except ValueError:
        return 30.0


class AuditableEventScorer:
    CATEGORY_MAGNITUDE = {
        "Foundation Model": 1.8,
        "AI Agent": 1.2,
        "AI Coding": 1.0,
        "Multimodal / AIGC": 1.0,
        "AI Product": 0.8,
        "Enterprise Adoption": 0.7,
        "Research": 1.3,
        "Open Source": 1.3,
        "AI Safety": 1.6,
        "Cybersecurity": 1.6,
        "Policy / Regulation": 1.8,
        "Funding / Business": 1.4,
        "Other": 0.4,
    }

    @staticmethod
    def _text(articles: list[StoredArticle]) -> str:
        return " ".join(
            f"{article.title} {article.summary or ''} {article.content or article.raw_text}"
            for article in articles
        ).casefold()

    @staticmethod
    def _contains(text: str, terms: tuple[str, ...]) -> int:
        return sum(1 for term in terms if term in text)

    def explain(self, event: Event, articles: list[StoredArticle]) -> ImportanceBreakdown:
        if not articles:
            return ImportanceBreakdown(0, 0, 0, 0, 0, 0, 0, 0, 0)

        text = self._text(articles)
        novelty = min(
            1.5,
            self._contains(
                text,
                (
                    "launch", "release", "introducing", "new model", "breakthrough",
                    "first", "state-of-the-art", "open weights",
                ),
            ) * 0.35,
        )
        if any(term in text for term in ("case study", "customer journey", "how we use")):
            novelty = min(novelty, 0.35)

        magnitude = self.CATEGORY_MAGNITUDE.get(event.category, 0.4)
        if any(term in text for term in ("industry-wide", "regulation", "acquisition", "security incident")):
            magnitude = min(2.0, magnitude + 0.2)

        source_types = [
            classify_source_type(article.url, article.source, event.title) for article in articles
        ]
        authority_values = {
            "official": 1.0,
            "research": 1.1,
            "independent_media": 0.8,
            "community": 0.4,
            "other": 0.3,
        }
        authority = min(
            1.2,
            sum(authority_values[item] for item in source_types) / len(source_types),
        )
        unique_sources = {article.source.casefold() for article in articles}
        diversity = min(1.2, max(0, len(unique_sources) - 1) * 0.6)
        if len(set(source_types)) >= 2:
            diversity = min(1.4, diversity + 0.2)

        ecosystem = min(
            1.4,
            self._contains(
                text,
                (
                    "open source", "open-source", "open weights", "api", "platform",
                    "ecosystem", "standard", "integration", "partnership",
                ),
            ) * 0.28,
        )
        developer = min(
            0.9,
            self._contains(
                text,
                ("developer", "coding", "code", "api", "sdk", "software engineering", "github"),
            ) * 0.18,
        )
        creator = min(
            0.8,
            self._contains(
                text,
                (
                    "creator", "content creation", "image generation", "video generation",
                    "music generation", "short video", "creative control",
                ),
            ) * 0.2,
        )
        newest_age = min(_age_days(article) for article in articles)
        recency = 0.8 if newest_age <= 2 else 0.6 if newest_age <= 7 else 0.3 if newest_age <= 30 else 0.0

        values = (novelty, magnitude, authority, diversity, ecosystem, developer, creator, recency)
        total = round(min(10.0, sum(values)), 2)
        return ImportanceBreakdown(
            novelty=round(novelty, 2), industry_magnitude=round(magnitude, 2),
            source_authority=round(authority, 2), source_diversity=round(diversity, 2),
            ecosystem_impact=round(ecosystem, 2), developer_impact=round(developer, 2),
            creator_impact=round(creator, 2), recency=round(recency, 2), total=total,
        )

    def score(self, event: Event, articles: list[StoredArticle]) -> float:
        return self.explain(event, articles).total
