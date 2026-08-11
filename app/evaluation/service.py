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
            saved.append(
                self.repository.save(
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

