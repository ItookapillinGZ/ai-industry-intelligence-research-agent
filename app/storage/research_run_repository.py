from __future__ import annotations

import json
from dataclasses import asdict

from app.models import (
    EvidenceReference,
    Event,
    ResearchBrief,
    ResearchSource,
    UGCRelevance,
    utc_now_iso,
)
from app.storage.database import Database
from app.storage.event_repository import event_from_row


def _ugc_from_json(value: str) -> UGCRelevance:
    try:
        data = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        data = None
    if isinstance(data, dict):
        return UGCRelevance(
            level=str(data.get("level", "low")),
            reason=str(data.get("reason", "")),
            affected_areas=[str(item) for item in data.get("affected_areas", [])],
        )
    text = str(value or "")
    level = "high" if text.casefold().startswith("high") else "medium" if text.casefold().startswith("medium") else "low"
    return UGCRelevance(level=level, reason=text, affected_areas=[])


def brief_from_row(row) -> ResearchBrief:
    return ResearchBrief(
        id=row["id"],
        event_id=row["event_id"],
        headline=row["headline"],
        executive_summary=row["executive_summary"],
        what_happened=row["what_happened"],
        key_facts=json.loads(row["key_facts"] or "[]"),
        background=row["background"],
        why_it_matters=row["why_it_matters"],
        industry_impact=row["industry_impact"],
        ugc_relevance=_ugc_from_json(row["ugc_relevance"]),
        evidence=[EvidenceReference(**item) for item in json.loads(row["evidence"] or "[]")],
        sources=[ResearchSource(**item) for item in json.loads(row["sources"] or "[]")],
        uncertainties=json.loads(row["uncertainties"] or "[]"),
        confidence=float(row["confidence"]),
        tags=json.loads(row["tags"] or "[]"),
        provider_name=row["provider_name"],
        research_mode=row["research_mode"],
        generation_type=row["generation_type"],
        evidence_pack_id=row["evidence_pack_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        model_name=row["model_name"],
        usage=json.loads(row["usage"] or "{}"),
    )


class ResearchRunRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def save(self, brief: ResearchBrief) -> ResearchBrief:
        now = utc_now_iso()
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO research_brief_runs (
                    event_id, research_mode, generation_type, evidence_pack_id,
                    headline, executive_summary, what_happened, key_facts,
                    background, why_it_matters, industry_impact, ugc_relevance,
                    evidence, sources, uncertainties, confidence, tags, provider_name,
                    model_name, usage, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id, research_mode, generation_type) DO UPDATE SET
                    evidence_pack_id = excluded.evidence_pack_id,
                    headline = excluded.headline,
                    executive_summary = excluded.executive_summary,
                    what_happened = excluded.what_happened,
                    key_facts = excluded.key_facts,
                    background = excluded.background,
                    why_it_matters = excluded.why_it_matters,
                    industry_impact = excluded.industry_impact,
                    ugc_relevance = excluded.ugc_relevance,
                    evidence = excluded.evidence,
                    sources = excluded.sources,
                    uncertainties = excluded.uncertainties,
                    confidence = excluded.confidence,
                    tags = excluded.tags,
                    provider_name = excluded.provider_name,
                    model_name = excluded.model_name,
                    usage = excluded.usage,
                    updated_at = excluded.updated_at
                """,
                (
                    brief.event_id,
                    brief.research_mode,
                    brief.generation_type,
                    brief.evidence_pack_id,
                    brief.headline,
                    brief.executive_summary,
                    brief.what_happened,
                    json.dumps(brief.key_facts, ensure_ascii=False),
                    brief.background,
                    brief.why_it_matters,
                    brief.industry_impact,
                    json.dumps(
                        asdict(
                            brief.ugc_relevance
                            if isinstance(brief.ugc_relevance, UGCRelevance)
                            else _ugc_from_json(str(brief.ugc_relevance))
                        ),
                        ensure_ascii=False,
                    ),
                    json.dumps([asdict(item) for item in brief.evidence], ensure_ascii=False),
                    json.dumps([asdict(item) for item in brief.sources], ensure_ascii=False),
                    json.dumps(brief.uncertainties, ensure_ascii=False),
                    max(0.0, min(1.0, brief.confidence)),
                    json.dumps(brief.tags, ensure_ascii=False),
                    brief.provider_name,
                    brief.model_name,
                    json.dumps(brief.usage, ensure_ascii=False),
                    brief.created_at or now,
                    now,
                ),
            )
            row = connection.execute(
                """
                SELECT * FROM research_brief_runs
                WHERE event_id = ? AND research_mode = ? AND generation_type = ?
                """,
                (brief.event_id, brief.research_mode, brief.generation_type),
            ).fetchone()
        return brief_from_row(row)

    def get_by_event(
        self,
        event_id: int,
        research_mode: str | None = None,
        generation_type: str | None = None,
    ) -> ResearchBrief | None:
        clauses = ["event_id = ?"]
        parameters: list[object] = [event_id]
        if research_mode:
            clauses.append("research_mode = ?")
            parameters.append(research_mode)
        if generation_type:
            clauses.append("generation_type = ?")
            parameters.append(generation_type)
        with self.database.connect() as connection:
            row = connection.execute(
                f"""
                SELECT * FROM research_brief_runs
                WHERE {' AND '.join(clauses)}
                ORDER BY CASE generation_type
                    WHEN 'live' THEN 0 WHEN 'deterministic' THEN 1
                    WHEN 'fallback' THEN 2 WHEN 'mock' THEN 3 ELSE 4 END,
                    updated_at DESC
                LIMIT 1
                """,
                tuple(parameters),
            ).fetchone()
        return brief_from_row(row) if row else None

    def get(self, brief_id: int) -> ResearchBrief | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM research_brief_runs WHERE id = ?", (brief_id,)
            ).fetchone()
        return brief_from_row(row) if row else None

    def list_with_events(
        self,
        limit: int,
        research_mode: str | None = None,
        generation_type: str | None = None,
    ) -> list[tuple[Event, ResearchBrief]]:
        clauses: list[str] = []
        parameters: list[object] = []
        if research_mode:
            clauses.append("rb.research_mode = ?")
            parameters.append(research_mode)
        if generation_type:
            clauses.append("rb.generation_type = ?")
            parameters.append(generation_type)
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        parameters.append(limit)
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT e.*, rb.id AS brief_id
                FROM events e
                JOIN research_brief_runs rb ON rb.event_id = e.id
                {where}
                ORDER BY e.importance_score DESC, rb.updated_at DESC
                LIMIT ?
                """,
                tuple(parameters),
            ).fetchall()
            results = []
            for row in rows:
                brief_row = connection.execute(
                    "SELECT * FROM research_brief_runs WHERE id = ?", (row["brief_id"],)
                ).fetchone()
                results.append((event_from_row(row), brief_from_row(brief_row)))
        return results

    def count(self, research_mode: str | None = None, generation_type: str | None = None) -> int:
        clauses: list[str] = []
        parameters: list[object] = []
        if research_mode:
            clauses.append("research_mode = ?")
            parameters.append(research_mode)
        if generation_type:
            clauses.append("generation_type = ?")
            parameters.append(generation_type)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM research_brief_runs" + where,
                tuple(parameters),
            ).fetchone()
        return int(row["count"])
