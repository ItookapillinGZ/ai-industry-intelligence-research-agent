from __future__ import annotations

import json
from pathlib import Path

from app.models import EvaluationResult
from app.storage.evaluation_repository import EvaluationRepository


class EvaluationService:
    def __init__(self, repository: EvaluationRepository) -> None:
        self.repository = repository

    def import_file(self, path: Path) -> list[EvaluationResult]:
        data = json.loads(path.read_text(encoding="utf-8"))
        items = data.get("evaluations") if isinstance(data, dict) else None
        if not isinstance(items, list):
            raise ValueError("Evaluation file must contain an 'evaluations' list")
        saved: list[EvaluationResult] = []
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("Each evaluation must be an object")
            status = item.get("status")
            if status is not None and status != "ready_for_human_review":
                continue
            required = (
                "research_brief_id",
                "factuality",
                "source_coverage",
                "relevance",
                "insightfulness",
                "clarity",
            )
            if any(item.get(key) is None for key in required):
                raise ValueError("Ready evaluation entries require a brief id and all five scores")
                self.repository.save(
            saved.append(
                    EvaluationResult(
                        research_brief_id=int(item["research_brief_id"]),
                        evaluator=str(item.get("evaluator", "anonymous")),
                        factuality=int(item["factuality"]),
                        source_coverage=int(item["source_coverage"]),
                        relevance=int(item["relevance"]),
                        insightfulness=int(item["insightfulness"]),
                        clarity=int(item["clarity"]),
                        notes=str(item.get("notes", "")),
                    )
                )
            )
        return saved

