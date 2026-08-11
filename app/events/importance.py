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
    """Score industry importance; source coverage remains a small audit component."""

    CATEGORY_MAGNITUDE = {
        "Foundation Model": 2.3,
        "AI Agent": 1.4,
        "AI Coding": 1.4,
        "Multimodal / AIGC": 1.4,
        "AI Product": 1.0,
        "Enterprise Adoption": 0.8,
        "Research": 1.5,
        "Open Source": 1.6,
        "AI Safety": 1.7,
        "Cybersecurity": 1.7,
        "Policy / Regulation": 2.0,
        "Funding / Business": 1.1,
        "Other": 0.5,
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
            1.6,
            self._contains(
                text,
                (
                    "launch", "release", "introducing", "new model", "breakthrough",
                    "state-of-the-art", "open weights", "open-source",
                ),
            ) * 0.4,
        )
        release_language = any(
            term in text for term in ("introducing", "model release", "new model", "model launched", "launches gpt", "available today")
        )
        major_model_release = event.category == "Foundation Model" and release_language
        if major_model_release:
            novelty = max(novelty, 1.4)

        magnitude = self.CATEGORY_MAGNITUDE.get(event.category, 0.5)
        if release_language and "model" in text:
            novelty = max(novelty, 1.2)
            magnitude = max(magnitude, 1.4)
        if any(term in text for term in ("industry-wide", "regulation", "acquisition", "security incident")):
            magnitude = min(2.5, magnitude + 0.2)

        limited_pilot = any(
            term in text for term in ("limited pilot", "limited-access pilot", "initial cohort", "pilot schools")
        )
        product_packaging = any(
            term in text for term in (
                "premium seats", "subscription tier", "pricing update", "usage limit", "per user per month",
            )
        )
        case_study = any(term in text for term in ("case study", "customer journey", "how we use"))
        if limited_pilot:
            novelty = min(novelty, 0.45)
            magnitude = min(magnitude, 0.65)
        if product_packaging:
            novelty = min(novelty, 0.45)
            magnitude = min(magnitude, 0.7)
        if case_study:
            novelty = min(novelty, 0.3)
            magnitude = min(magnitude, 0.65)

        source_types = [
            classify_source_type(article.url, article.source, event.title) for article in articles
        ]
        authority_values = {
            "official": 1.0,
            "research": 1.0,
            "independent_media": 0.8,
            "community": 0.4,
            "other": 0.3,
        }
        source_authority = min(
            0.3,
            0.3 * sum(authority_values[item] for item in source_types) / len(source_types),
        )
        unique_sources = {article.source.casefold() for article in articles}
        source_diversity = min(0.15, max(0, len(unique_sources) - 1) * 0.05)
        if "official" in source_types and "independent_media" in source_types:
            source_diversity = min(0.2, source_diversity + 0.05)

        ecosystem = min(
            1.6,
            self._contains(
                text,
                (
                    "open source", "open-source", "open weights", "api", "platform",
                    "ecosystem", "standard", "integration", "partnership",
                ),
            ) * 0.32,
        )
        developer = min(
            1.1,
            self._contains(
                text,
                ("developer", "coding", "code", "api", "sdk", "software engineering", "github"),
            ) * 0.22,
        )
        creator = min(
            0.8,
            self._contains(
                text,
                (
                    "creator", "content creation", "image generation", "video generation",
                    "music generation", "short video", "creative control", "dubbing", "narration",
                ),
            ) * 0.2,
        )
        newest_age = min(_age_days(article) for article in articles)
        recency = 0.6 if newest_age <= 2 else 0.45 if newest_age <= 7 else 0.25 if newest_age <= 30 else 0.0

        values = (
            novelty, magnitude, source_authority, source_diversity,
            ecosystem, developer, creator, recency,
        )
        total = round(min(10.0, sum(values)), 2)
        return ImportanceBreakdown(
            novelty=round(novelty, 2),
            industry_magnitude=round(magnitude, 2),
            source_authority=round(source_authority, 2),
            source_diversity=round(source_diversity, 2),
            ecosystem_impact=round(ecosystem, 2),
            developer_impact=round(developer, 2),
            creator_impact=round(creator, 2),
            recency=round(recency, 2),
            total=total,
        )

    def score(self, event: Event, articles: list[StoredArticle]) -> float:
        return self.explain(event, articles).total
