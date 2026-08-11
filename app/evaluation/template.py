from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.storage.event_repository import EventRepository
from app.storage.research_repository import ResearchRepository


class ResearchEvaluationTemplateGenerator:
    MODES = ("deterministic", "single_source_llm", "multi_source_llm")

    def __init__(
        self,
        event_repository: EventRepository,
        research_repository: ResearchRepository,
        output_dir: Path,
        live_llm_configured: bool,
    ) -> None:
        self.event_repository = event_repository
        self.research_repository = research_repository
        self.output_dir = output_dir
        self.live_llm_configured = live_llm_configured

    def generate(self, top_k: int = 10) -> Path:
        events = self.event_repository.list_events(limit=top_k)
        items = []
        for event in events:
            for mode in self.MODES:
                brief = self.research_repository.get_by_event(event.id, research_mode=mode)
                if brief is None:
                    status = (
                        "blocked_missing_api_key"
                        if mode != "deterministic" and not self.live_llm_configured
                        else "not_generated"
                    )
                    generation_type = None
                    brief_id = None
                else:
                    generation_type = brief.generation_type
                    brief_id = brief.id
                    status = {
                        "live": "ready_for_human_review",
                        "deterministic": "ready_for_human_review",
                        "mock": "mock_only_not_live_validation",
                        "fallback": (
                            "blocked_missing_api_key_fallback_generated"
                            if mode != "deterministic" and not self.live_llm_configured
                            else "fallback_not_llm"
                        ),
                        "legacy_unverified": "legacy_unverified",
                    }.get(generation_type, "not_generated")
                items.append(
                    {
                        "event_id": event.id,
                        "event_title": event.title,
                        "research_mode": mode,
                        "generation_type": generation_type,
                        "research_brief_id": brief_id,
                        "status": status,
                        "evaluator": "replace-with-reviewer",
                        "factuality": None,
                        "source_coverage": None,
                        "relevance": None,
                        "insightfulness": None,
                        "clarity": None,
                        "notes": "",
                    }
                )
        payload = {
            "instructions": (
                "Fill 1-5 scores only for records with status ready_for_human_review. "
                "Mock, fallback, blocked, and legacy-unverified records must not be reported "
                "as successful live LLM validation."
            ),
            "dimensions": [
                "factuality", "source_coverage", "relevance", "insightfulness", "clarity"
            ],
            "events": len(events),
            "evaluations": items,
        }
        self.output_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = self.output_dir / f"research_quality_template_{now}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path
