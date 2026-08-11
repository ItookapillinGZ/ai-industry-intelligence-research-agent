from __future__ import annotations

from pathlib import Path

from app.models import Event, StoredArticle
from app.research.factory import ResilientResearchAgent
from app.research.fallback import DeterministicResearchAgent
from app.research.llm_agent import LLMResearchAgent


class InvalidJsonProvider:
    name = "invalid-json-provider"

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        return "This is not JSON."


def test_invalid_llm_json_uses_deterministic_fallback(tmp_path: Path) -> None:
    (tmp_path / "research_system.txt").write_text("system", encoding="utf-8")
    (tmp_path / "research_event.txt").write_text(
        "{{EVENT_JSON}} {{ARTICLES_JSON}}", encoding="utf-8"
    )
    event = Event(
        id=1,
        title="Test event",
        normalized_title="test event",
        category="Other",
        created_at="2026-08-11T00:00:00+00:00",
        updated_at="2026-08-11T00:00:00+00:00",
        importance_score=5,
        article_count=1,
        source_count=1,
    )
    article = StoredArticle(
        id=1,
        title="Test event source",
        url="https://example.com/source",
        source="Example",
        author=None,
        published_at="2026-08-11T00:00:00+00:00",
        collected_at="2026-08-11T00:00:00+00:00",
        raw_text="Reported source evidence.",
        summary="Reported source evidence.",
        category="Other",
        importance_score=5,
        tags=[],
        normalized_url="https://example.com/source",
        normalized_title="test event source",
        processing_status="processed",
        llm_provider="test",
    )
    agent = ResilientResearchAgent(
        LLMResearchAgent(InvalidJsonProvider(), tmp_path),
        DeterministicResearchAgent(),
    )

    brief = agent.research(event, [article])

    assert brief.provider_name == "local-research-fallback"
    assert brief.sources[0].url == "https://example.com/source"

