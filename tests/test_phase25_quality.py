from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from app.analysis.fallback import KeywordClassifier
from app.evaluation.service import EvaluationService
from app.analysis.taxonomy import CATEGORIES
from app.evaluation.template import ResearchEvaluationTemplateGenerator
from app.evidence.gatherers import SearchEvidenceGatherer, SeedEvidenceGatherer
from app.evidence.interfaces import SearchResult
from app.events.importance import AuditableEventScorer
from app.models import (
    Event,
    ResearchBrief,
    StoredArticle,
    UGCRelevance,
)
from app.research.evidence_analyst import (
    DeterministicEvidenceAnalyst,
    EvidenceBoundLLMAnalyst,
)
from app.storage.event_repository import EventRepository
from app.storage.research_repository import ResearchRepository
from app.storage.evaluation_repository import EvaluationRepository


def _article(
    article_id: int,
    title: str,
    url: str,
    source: str,
    content: str,
    category: str = "Other",
) -> StoredArticle:
    now = datetime.now(timezone.utc).isoformat()
    return StoredArticle(
        id=article_id,
        title=title,
        url=url,
        source=source,
        author=None,
        published_at=now,
        collected_at=now,
        raw_text=content,
        summary=content,
        category=category,
        importance_score=5.0,
        tags=[],
        normalized_url=url,
        normalized_title=title.casefold(),
        processing_status="processed",
        llm_provider="test",
        content=content,
        content_status="fetched",
        content_length=len(content),
    )


def _event(event_id: int, title: str, category: str) -> Event:
    now = datetime.now(timezone.utc).isoformat()
    return Event(
        id=event_id,
        title=title,
        normalized_title=title.casefold(),
        category=category,
        created_at=now,
        updated_at=now,
        importance_score=0,
        article_count=1,
        source_count=1,
    )


class StaticSearch:
    def search(self, query: str, limit: int) -> list[SearchResult]:
        return [
            SearchResult(
                title="OpenAI frontier model launch independent report",
                source="Reuters",
                url="https://reuters.com/technology/model-launch?utm_source=search",
                snippet="Reuters independently reported the launch.",
            ),
            SearchResult(
                title="OpenAI frontier model launch independent report",
                source="Reuters",
                url="https://reuters.com/technology/model-launch",
                snippet="Duplicate URL after normalization.",
            ),
            SearchResult(
                title="OpenAI frontier model launch industry analysis",
                source="TechCrunch",
                url="https://techcrunch.com/ai/model-launch",
                snippet="An additional independent account.",
            ),
        ][:limit]


class FailingSearch:
    def search(self, query: str, limit: int) -> list[SearchResult]:
        raise TimeoutError("search unavailable")


class MockProvider:
    name = "mock-provider"

    def __init__(self, response: dict) -> None:
        self.response = response
        self.system_prompt = ""
        self.user_prompt = ""

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        return json.dumps(self.response)


def test_taxonomy_covers_phase25_categories_and_cyber_is_not_coding() -> None:
    required = {
        "Foundation Model", "AI Agent", "AI Coding", "Multimodal / AIGC",
        "AI Product", "Enterprise Adoption", "Research", "Open Source",
        "AI Safety", "Cybersecurity", "Policy / Regulation",
        "Funding / Business", "Other",
    }
    assert required <= set(CATEGORIES)
    article = _article(
        1,
        "Third-party cyber evaluations involving OpenAI models",
        "https://openai.com/research/cyber-evaluations",
        "OpenAI News",
        "Independent evaluators tested cybersecurity capability and misuse risk.",
    )
    assert KeywordClassifier().classify(article).category == "Cybersecurity"


def test_evidence_gathering_deduplicates_and_records_coverage() -> None:
    event = _event(1, "OpenAI launches a new frontier model", "Foundation Model")
    seed = _article(
        1,
        event.title,
        "https://openai.com/index/new-frontier-model",
        "OpenAI News",
        "OpenAI announced a new model.",
    )
    pack = SearchEvidenceGatherer(StaticSearch()).gather(event, [seed])
    assert len({item.url for item in pack.items}) == len(pack.items)
    assert any(item.source_type == "official" for item in pack.items)
    assert sum(item.source_type == "independent_media" for item in pack.items) >= 1
    assert pack.coverage_status == "sufficient"
    assert all(item.url.startswith("https://") for item in pack.items)


def test_search_failure_keeps_seed_evidence_and_does_not_raise() -> None:
    event = _event(1, "Model security evaluation", "Cybersecurity")
    seed = _article(
        1,
        event.title,
        "https://openai.com/research/security",
        "OpenAI News",
        "A security evaluation was published.",
    )
    pack = SearchEvidenceGatherer(FailingSearch()).gather(event, [seed])
    assert len(pack.items) == 1
    assert pack.coverage_status == "insufficient"
    assert len(pack.errors) == 3


def test_mock_llm_uses_real_prompts_and_is_marked_mock() -> None:
    event = _event(1, "OpenAI launches a new model", "Foundation Model")
    article = _article(
        1,
        event.title,
        "https://openai.com/index/model",
        "OpenAI News",
        "OpenAI released a new foundation model.",
    )
    pack = SeedEvidenceGatherer("single_source_llm", 1).gather(event, [article])
    item = pack.items[0]
    payload = {
        "headline": event.title,
        "executive_summary": "OpenAI released a model.",
        "what_happened": "OpenAI released a model.",
        "key_facts": [
            {
                "statement": "OpenAI released a model.",
                "type": "reported_fact",
                "source_ids": [item.source_id],
            }
        ],
        "background": "No additional background is supplied.",
        "why_it_matters": "The release may affect model competition.",
        "industry_impact": "Impact remains uncertain.",
        "ugc_relevance": {
            "level": "low",
            "directness": "none",
            "reason": "No direct creator impact is supplied.",
            "affected_areas": [],
        },
        "evidence": [
            {
                "claim": "OpenAI released a model.",
                "source_id": item.source_id,
                "url": item.url,
                "evidence_text": "OpenAI released a new foundation model.",
                "evidence_type": "verbatim_quote",
            }
        ],
        "sources": [{"source_id": item.source_id, "url": item.url}],
        "uncertainties": ["Only one source is supplied."],
        "claim_confidence": 0.65,
        "verification_level": "single_first_party",
        "tags": ["Foundation Model"],
    }
    provider = MockProvider(payload)
    brief = EvidenceBoundLLMAnalyst(
        provider,
        Path("prompts"),
        research_mode="single_source_llm",
        generation_type="mock",
    ).analyze(event, pack)
    assert brief.generation_type == "mock"
    assert brief.provider_name == "mock-provider"
    assert "Evidence Pack" in provider.system_prompt
    assert item.source_id in provider.user_prompt
    assert brief.sources[0].url == article.url


def test_research_run_repository_prevents_mock_or_fallback_overwriting_live(repository) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with repository.database.connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO events (
                title, normalized_title, category, created_at, updated_at,
                importance_score, article_count, source_count
            ) VALUES ('Event', 'event', 'Research', ?, ?, 5, 1, 1)
            """,
            (now, now),
        )
        event_id = int(cursor.lastrowid)
    runs = ResearchRepository(repository.database)

    def brief(generation_type: str, headline: str) -> ResearchBrief:
        return ResearchBrief(
            event_id=event_id,
            headline=headline,
            executive_summary="Summary",
            what_happened="What",
            key_facts=[],
            background="Background",
            why_it_matters="Why",
            industry_impact="Impact",
            ugc_relevance=UGCRelevance("low", "none", "No direct impact.", []),
            evidence=[],
            sources=[],
            uncertainties=[],
            claim_confidence=0.5,
            verification_level="single_first_party",
            tags=[],
            provider_name="test",
            research_mode="single_source_llm",
            generation_type=generation_type,
        )

    live = runs.save(brief("live", "Live result"))
    runs.save(brief("mock", "Mock result"))
    runs.save(brief("fallback", "Fallback result"))
    assert runs.count("single_source_llm") == 3
    assert runs.get_by_event(event_id, "single_source_llm").id == live.id
    assert runs.get(live.id).headline == "Live result"


def test_importance_breakdown_penalizes_single_source_case_study_naturally() -> None:
    scorer = AuditableEventScorer()
    case_event = _event(
        1,
        "Virgin Atlantic sharpens customer journeys with ChatGPT Work",
        "Enterprise Adoption",
    )
    case_article = _article(
        1,
        case_event.title,
        "https://openai.com/customers/virgin-atlantic",
        "OpenAI News",
        "A customer case study describes one enterprise customer journey.",
        "Enterprise Adoption",
    )
    model_event = _event(2, "Introducing a new frontier model release", "Foundation Model")
    model_article = _article(
        2,
        model_event.title,
        "https://openai.com/index/frontier-model",
        "OpenAI News",
        "The release adds a new API, developer integration, and model capability.",
        "Foundation Model",
    )
    case = scorer.explain(case_event, [case_article])
    model = scorer.explain(model_event, [model_article])
    assert set(asdict(case)) == {
        "novelty", "industry_magnitude", "source_authority", "source_diversity",
        "ecosystem_impact", "developer_impact", "creator_impact", "recency", "total",
    }
    assert model.total > case.total
    assert case.source_diversity == 0


def test_ugc_low_is_honest_when_evidence_has_no_direct_relationship() -> None:
    event = _event(1, "Third-party cyber evaluations", "Cybersecurity")
    article = _article(
        1,
        event.title,
        "https://openai.com/research/cyber",
        "OpenAI News",
        "The report evaluates cybersecurity performance.",
    )
    pack = SeedEvidenceGatherer("deterministic").gather(event, [article])
    brief = DeterministicEvidenceAnalyst().analyze(event, pack)
    assert brief.ugc_relevance.level == "low"
    assert brief.ugc_relevance.affected_areas == []


def test_evaluation_template_has_three_states_for_ten_events(repository, tmp_path: Path) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with repository.database.connect() as connection:
        for index in range(10):
            connection.execute(
                """
                INSERT INTO events (
                    title, normalized_title, category, created_at, updated_at,
                    importance_score, article_count, source_count
                ) VALUES (?, ?, 'Other', ?, ?, ?, 1, 1)
                """,
                (f"Event {index}", f"event {index}", now, now, 10 - index),
            )
    path = ResearchEvaluationTemplateGenerator(
        EventRepository(repository.database),
        ResearchRepository(repository.database),
        tmp_path,
        live_llm_configured=False,
    ).generate(10)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["events"] == 10
    assert len(data["evaluations"]) == 30
    blocked = [item for item in data["evaluations"] if item["status"] == "blocked_missing_api_key"]
    assert len(blocked) == 20


def test_blocked_template_entries_are_not_imported_as_scores(repository, tmp_path: Path) -> None:
    path = test_path = tmp_path / "template.json"
    test_path.write_text(
        json.dumps(
            {
                "evaluations": [
                    {
                        "status": "blocked_missing_api_key",
                        "research_brief_id": None,
                        "factuality": None,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    assert EvaluationService(EvaluationRepository(repository.database)).import_file(path) == []


def test_cli_main_initializes_args_inside_main(monkeypatch) -> None:
    import app.cli as cli

    monkeypatch.setattr(cli, "_runtime", lambda *_args: (object(), object()))
    monkeypatch.setattr(cli, "_reclassify", lambda _config, _repository, limit: 0)
    assert cli.main(["reclassify", "--limit", "1"]) == 0
