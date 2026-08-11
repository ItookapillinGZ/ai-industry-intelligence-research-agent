from __future__ import annotations

from app.models import EvaluationResult, utc_now_iso
from app.storage.database import Database


class EvaluationRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def save(self, result: EvaluationResult) -> EvaluationResult:
        scores = (
            result.factuality,
            result.source_coverage,
            result.relevance,
            result.insightfulness,
            result.clarity,
        )
        if any(score < 1 or score > 5 for score in scores):
            raise ValueError("Evaluation scores must be between 1 and 5")
        now = utc_now_iso()
        with self.database.connect() as connection:
            exists = connection.execute(
                "SELECT 1 FROM research_brief_runs WHERE id = ?", (result.research_brief_id,)
            ).fetchone()
            if not exists:
                raise ValueError(f"ResearchBrief not found: {result.research_brief_id}")
            cursor = connection.execute(
                """
                INSERT INTO research_evaluations (
                    research_brief_id, evaluator, factuality, source_coverage,
                    relevance, insightfulness, clarity, notes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.research_brief_id,
                    result.evaluator,
                    result.factuality,
                    result.source_coverage,
                    result.relevance,
                    result.insightfulness,
                    result.clarity,
                    result.notes,
                    now,
                ),
            )
        result.id = int(cursor.lastrowid)
        result.created_at = now
        return result

    def list_with_headlines(self) -> list[tuple[EvaluationResult, str]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT e.*, rb.headline
                FROM research_evaluations e
                JOIN research_brief_runs rb ON rb.id = e.research_brief_id
                ORDER BY e.created_at DESC, e.id DESC
                """
            ).fetchall()
        return [
            (
                EvaluationResult(
                    id=row["id"],
                    research_brief_id=row["research_brief_id"],
                    evaluator=row["evaluator"],
                    factuality=row["factuality"],
                    source_coverage=row["source_coverage"],
                    relevance=row["relevance"],
                    insightfulness=row["insightfulness"],
                    clarity=row["clarity"],
                    notes=row["notes"],
                    created_at=row["created_at"],
                ),
                row["headline"],
            )
            for row in rows
        ]

    def count(self) -> int:

        with self.database.connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM research_evaluations").fetchone()
        return int(row["count"])
    def list_with_context(
        self,
    ) -> list[tuple[EvaluationResult, str, str, str, int]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT e.*, rb.headline, rb.research_mode, rb.generation_type, rb.event_id
                FROM research_evaluations e
                JOIN research_brief_runs rb ON rb.id = e.research_brief_id
                ORDER BY e.created_at DESC, e.id DESC
                """
            ).fetchall()
        return [
            (
                EvaluationResult(
                    id=row["id"], research_brief_id=row["research_brief_id"],
                    evaluator=row["evaluator"], factuality=row["factuality"],
                    source_coverage=row["source_coverage"], relevance=row["relevance"],
                    insightfulness=row["insightfulness"], clarity=row["clarity"],
                    notes=row["notes"], created_at=row["created_at"],
                ),
                row["headline"],
                row["research_mode"],
                row["generation_type"],
                row["event_id"],
            )
            for row in rows
        ]

