from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from app.evidence.source_types import SOURCE_TYPES
from app.evaluation.live_comparison_reporter import LiveResearchComparisonReportGenerator
from app.models import ResearchBrief, UGCRelevance
from app.research.evidence_analyst import ResearchValidationError, _json_object
from app.storage.research_repository import ResearchRepository


def _event_id(repository) -> int:
    now = datetime.now(timezone.utc).isoformat()
    with repository.database.connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO events (
                title, normalized_title, category, created_at, updated_at,
                importance_score, article_count, source_count
            ) VALUES ('Live validation event', 'live validation event', 'Research', ?, ?, 9, 1, 1)
            """,
            (now, now),
        )
        return int(cursor.lastrowid)


def _brief(
    event_id: int,
    mode: str,
    generation_type: str,
    provider: str,
    model: str | None = None,
) -> ResearchBrief:
    return ResearchBrief(
        event_id=event_id,
        headline=f"{mode} headline",
        executive_summary="Summary",
        what_happened="What happened",
        key_facts=[],
        background="Background",
        why_it_matters="Why",
        industry_impact="Impact",
        ugc_relevance=UGCRelevance("low", "No direct effect.", []),
        evidence=[],
        sources=[],
        uncertainties=["Pending human review."],
        confidence=0.5,
        tags=["Research"],
        provider_name=provider,
        research_mode=mode,
        generation_type=generation_type,
        model_name=model,
        usage={"prompt_tokens": 10, "completion_tokens": 5} if model else {},
    )


def test_research_json_parser_rejects_surrounding_text() -> None:
    with pytest.raises(ResearchValidationError):
        _json_object('preface {"headline": "not strict"}')
    with pytest.raises(ResearchValidationError):
        _json_object('{"headline": "not strict"} trailing text')


def test_phase26_source_type_taxonomy_is_explicit() -> None:
    assert SOURCE_TYPES == (
        "official", "independent_media", "research", "community", "other"
    )




def test_live_model_and_usage_metadata_round_trip(repository) -> None:
    event_id = _event_id(repository)
    runs = ResearchRepository(repository.database)
    saved = runs.save(
        _brief(event_id, "single_source_llm", "live", "openai-compatible", "actual-model")
    )
    loaded = runs.get(saved.id)
    assert loaded.model_name == "actual-model"
    assert loaded.usage == {"prompt_tokens": 10, "completion_tokens": 5}


def test_live_comparison_excludes_fallback_and_keeps_scores_pending(
    repository, tmp_path
) -> None:
    event_id = _event_id(repository)
    runs = ResearchRepository(repository.database)
    runs.save(_brief(event_id, "deterministic", "deterministic", "local-research-fallback"))
    runs.save(
        _brief(event_id, "single_source_llm", "live", "openai-compatible", "actual-model")
    )
    runs.save(
        _brief(event_id, "single_source_llm", "fallback", "local-research-fallback")
    )
    runs.save(
        _brief(event_id, "multi_source_llm", "live", "openai-compatible", "actual-model")
    )
    report_path, dataset_path = LiveResearchComparisonReportGenerator(
        runs, tmp_path
    ).generate(1)
    data = json.loads(dataset_path.read_text(encoding="utf-8"))
    results = data["events"][0]["results"]
    assert [item["label"] for item in results] == [
        "deterministic",
        "live_single_source_llm",
        "live_multi_source_llm",
    ]
    assert results[1]["generation_type"] == "live"
    assert results[2]["generation_type"] == "live"
    assert data["excluded_historical_fallbacks"]["single_source_llm"] == 1
    assert data["human_quality_scores"] == "pending"
    assert results[1]["total_source_count"] == 0
    assert results[1]["official_source_count"] == 0
    assert results[1]["independent_source_count"] == 0
    assert results[1]["community_source_count"] == 0
    assert results[1]["independent_source_coverage"] == "insufficient"
    assert "Human quality scoring: **pending**" in report_path.read_text(
        encoding="utf-8"
    )
