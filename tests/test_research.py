from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.events.grouping import DeterministicEventGrouper
from app.events.service import EventGroupingService
from app.models import ArticleInput, ClassificationResult
from app.research.factory import ResilientResearchAgent
from app.research.fallback import DeterministicResearchAgent
from app.research.llm_agent import LLMResearchAgent, ResearchValidationError
from app.research.reporter import ResearchReportGenerator
from app.research.service import ResearchService
from app.services.normalizer import normalize_article
from app.storage.article_repository import ArticleRepository
from app.storage.event_repository import EventRepository
from app.storage.research_repository import ResearchRepository


class FakeProvider:
    name = "fake-llm"

    def __init__(self, response: str) -> None:
        self.response = response

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        return self.response


def _event_with_article(repository: ArticleRepository):
    article_id = repository.insert(
        normalize_article(
            ArticleInput(
                title="Open source image model improves video generation",
                url="https://example.com/real-source",
                source="Real Source",
                published_at=datetime.now(timezone.utc).isoformat(),
                raw_text="The project released an open source image model for video creators.",
                tags=["AIGC"],
            )
        )
    )
    repository.update_analysis(
        article_id,
        ClassificationResult(category="AIGC", tags=["video generation"]),
        7.5,
        "An open source image model was released.",
        ["AIGC"],
        "test",
    )
    repository.update_content_success(
        article_id,
        "The project released an open source image model for video creators. " * 10,
    )
    event_repository = EventRepository(repository.database)
    EventGroupingService(
        event_repository, DeterministicEventGrouper(), similarity_threshold=0.62
    ).group(10)
    return event_repository, event_repository.list_events()[0]


def test_deterministic_research_brief_schema(repository: ArticleRepository) -> None:
    event_repository, event = _event_with_article(repository)
    brief = DeterministicResearchAgent().research(event, event_repository.list_articles(event.id))
    assert brief.headline
    assert brief.key_facts[0]["type"] == "reported_fact"
    assert 0 <= brief.confidence <= 1
    assert brief.sources[0].url == "https://example.com/real-source"
    assert brief.ugc_relevance.level == "medium"
    assert "content_creation" in brief.ugc_relevance.affected_areas


def test_invalid_llm_json_gracefully_falls_back(
    repository: ArticleRepository, tmp_path: Path
) -> None:
    event_repository, event = _event_with_article(repository)
    primary = LLMResearchAgent(FakeProvider("not json"), tmp_path)
    agent = ResilientResearchAgent(primary, DeterministicResearchAgent())
    brief = agent.research(event, event_repository.list_articles(event.id))
    assert brief.provider_name == "local-research-fallback"


def test_fake_source_is_rejected(repository: ArticleRepository, tmp_path: Path) -> None:
    event_repository, event = _event_with_article(repository)
    (tmp_path / "research_system.txt").write_text("system", encoding="utf-8")
    (tmp_path / "research_event.txt").write_text("{{EVENT_JSON}} {{ARTICLES_JSON}}", encoding="utf-8")
    payload = {
        "headline": "Headline",
        "executive_summary": "Summary",
        "what_happened": "What",
        "key_facts": [],
        "background": "Background",
        "why_it_matters": "Why",
        "industry_impact": "Impact",
        "ugc_relevance": "Low relevance / limited direct impact",
        "evidence": [],
        "sources": [{"url": "https://fake.example/invented"}],
        "uncertainties": [],
        "claim_confidence": 0.5,
        "verification_level": "single_first_party",
        "tags": [],
    }
    agent = LLMResearchAgent(FakeProvider(json.dumps(payload)), tmp_path)
    with pytest.raises(ResearchValidationError, match="unknown source"):
        agent.research(event, event_repository.list_articles(event.id))


def test_research_persistence_and_report_real_urls(
    repository: ArticleRepository, tmp_path: Path
) -> None:
    event_repository, _event = _event_with_article(repository)
    research_repository = ResearchRepository(repository.database)
    stats = ResearchService(
        event_repository, research_repository, DeterministicResearchAgent()
    ).research_top_events(5)
    assert (stats.generated, stats.failed) == (1, 0)
    assert research_repository.count() == 1
    path = ResearchReportGenerator(research_repository, tmp_path / "reports").generate(5)
    report = path.read_text(encoding="utf-8")
    assert "## Top Events" in report
    assert "https://example.com/real-source" in report
    assert "fake.example" not in report

