from __future__ import annotations

import json
from dataclasses import asdict

from app.models import EvidenceReference, Event, ResearchBrief, ResearchSource, utc_now_iso
from app.storage.database import Database
from app.storage.event_repository import event_from_row


def _brief_from_row(row) -> ResearchBrief:
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
        ugc_relevance=row["ugc_relevance"],
        evidence=[EvidenceReference(**item) for item in json.loads(row["evidence"] or "[]")],
        sources=[ResearchSource(**item) for item in json.loads(row["sources"] or "[]")],
        uncertainties=json.loads(row["uncertainties"] or "[]"),
        confidence=float(row["confidence"]),
        tags=json.loads(row["tags"] or "[]"),
        provider_name=row["provider_name"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class ResearchRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def save(self, brief: ResearchBrief) -> ResearchBrief:
        now = utc_now_iso()
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO research_briefs (
                    event_id, headline, executive_summary, what_happened, key_facts,
                    background, why_it_matters, industry_impact, ugc_relevance,
                    evidence, sources, uncertainties, confidence, tags, provider_name,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id) DO UPDATE SET
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
                    updated_at = excluded.updated_at
                """,
                (
                    brief.event_id,
                    brief.headline,
                    brief.executive_summary,
                    brief.what_happened,
                    json.dumps(brief.key_facts, ensure_ascii=False),
                    brief.background,
                    brief.why_it_matters,
                    brief.industry_impact,
                    brief.ugc_relevance,
                    json.dumps([asdict(item) for item in brief.evidence], ensure_ascii=False),
                    json.dumps([asdict(item) for item in brief.sources], ensure_ascii=False),
                    json.dumps(brief.uncertainties, ensure_ascii=False),
                    max(0.0, min(1.0, brief.confidence)),
                    json.dumps(brief.tags, ensure_ascii=False),
                    brief.provider_name,
                    brief.created_at or now,
                    now,
                ),
            )
            row = connection.execute(
                "SELECT * FROM research_briefs WHERE event_id = ?", (brief.event_id,)
            ).fetchone()
        return _brief_from_row(row)

    def get_by_event(self, event_id: int) -> ResearchBrief | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM research_briefs WHERE event_id = ?", (event_id,)
            ).fetchone()
        return _brief_from_row(row) if row else None

    def get(self, brief_id: int) -> ResearchBrief | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM research_briefs WHERE id = ?", (brief_id,)
            ).fetchone()
        return _brief_from_row(row) if row else None

    def list_with_events(self, limit: int) -> list[tuple[Event, ResearchBrief]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT e.*, rb.id AS brief_id
                FROM events e
                JOIN research_briefs rb ON rb.event_id = e.id
                ORDER BY e.importance_score DESC, e.updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            results: list[tuple[Event, ResearchBrief]] = []
            for row in rows:
                brief_row = connection.execute(
                    "SELECT * FROM research_briefs WHERE id = ?", (row["brief_id"],)
                ).fetchone()
                results.append((event_from_row(row), _brief_from_row(brief_row)))
        return results

    def count(self) -> int:
        with self.database.connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM research_briefs").fetchone()
        return int(row["count"])


# Phase 2.5 uses the additive run table so deterministic, mock, and live results
# cannot overwrite one another. The Phase 2 implementation above remains migration context.
from app.storage.research_run_repository import ResearchRunRepository as ResearchRepository
