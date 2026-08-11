from __future__ import annotations

from app.analysis.fallback import ExtractiveSummarizer, KeywordClassifier
from app.models import StoredArticle


def test_analysis_prefers_full_content_over_rss_text() -> None:
    article = StoredArticle(
        id=1,
        title="Product update",
        url="https://example.com/article",
        source="Example",
        author=None,
        published_at=None,
        collected_at="2026-08-11T00:00:00+00:00",
        raw_text="Short product announcement.",
        summary=None,
        category=None,
        importance_score=None,
        tags=[],
        normalized_url="https://example.com/article",
        normalized_title="product update",
        processing_status="pending",
        llm_provider=None,
        content="The company released a new video generation diffusion model for creators.",
        content_status="fetched",
        content_length=76,
    )
    assert KeywordClassifier().classify(article).category == "AIGC"
    assert "video generation" in ExtractiveSummarizer().summarize(article)

