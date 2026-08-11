from __future__ import annotations

from pathlib import Path

import pytest

from app.evaluation.reporter import EvaluationReportGenerator
from app.models import EvaluationResult, ResearchBrief
from app.storage.evaluation_repository import EvaluationRepository
from app.storage.research_repository import ResearchRepository


def _brief(repository) -> ResearchBrief:
    database = repository.database
    with database.connect() as connection:
        now = "2026-08-11T00:00:00+00:00"
        cursor = connection.execute(
            """
            INSERT INTO events (
                title, normalized_title, category, created_at, updated_at,
                importance_score, article_count, source_count
            ) VALUES ('Test event', 'test event', 'LLM', ?, ?, 7, 1, 1)
            """,
            (now, now),
        )
        event_id = int(cursor.lastrowid)
    return ResearchRepository(database).save(
        ResearchBrief(
            event_id=event_id,
            headline="Test research brief",
            executive_summary="Summary",
            what_happened="What happened",
            key_facts=[],
            background="Background",
            why_it_matters="Why",
            industry_impact="Impact",
            ugc_relevance="Low relevance / limited direct impact",
            evidence=[],
            sources=[],
            uncertainties=["Limited evidence"],
            claim_confidence=0.5,
            verification_level="single_first_party",
            tags=["LLM"],
            provider_name="test",
        )
    )


def test_evaluation_persistence_and_summary(repository, tmp_path: Path) -> None:
    brief = _brief(repository)
    evaluation_repository = EvaluationRepository(repository.database)
    saved = evaluation_repository.save(
        EvaluationResult(
            research_brief_id=brief.id,
            evaluator="reviewer",
            factuality=5,
            source_coverage=4,
            relevance=4,
            insightfulness=3,
            clarity=5,
            notes="Clear but needs more independent sources.",
        )
    )
    assert saved.id is not None
    assert evaluation_repository.count() == 1
    path = EvaluationReportGenerator(evaluation_repository, tmp_path).generate()
    text = path.read_text(encoding="utf-8")
    assert "| factuality | 5.00/5 |" in text
    assert "| insightfulness | 3.00/5 |" in text
    assert "Test research brief" in text


def test_evaluation_scores_are_bounded(repository) -> None:
    brief = _brief(repository)
    with pytest.raises(ValueError, match="between 1 and 5"):
        EvaluationRepository(repository.database).save(
            EvaluationResult(
                research_brief_id=brief.id,
                evaluator="reviewer",
                factuality=6,
                source_coverage=3,
                relevance=3,
                insightfulness=3,
                clarity=3,
            )
        )
