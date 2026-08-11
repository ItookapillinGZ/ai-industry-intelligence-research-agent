from __future__ import annotations

import logging

from app.evidence.interfaces import EvidenceGatherer
from app.models import Event, ResearchBrief, StoredArticle
from app.research.evidence_analyst import DeterministicEvidenceAnalyst
from app.storage.evidence_repository import EvidencePackRepository

logger = logging.getLogger(__name__)


class ResearchWorkflow:
    def __init__(
        self,
        gatherer: EvidenceGatherer,
        analyst,
        evidence_repository: EvidencePackRepository,
        fallback: DeterministicEvidenceAnalyst | None = None,
    ) -> None:
        self.gatherer = gatherer
        self.analyst = analyst
        self.evidence_repository = evidence_repository
        self.fallback = fallback
        self.provider_name = analyst.provider_name
        self.research_mode = gatherer.mode
        self.generation_type = getattr(analyst, "generation_type", "live")

    def research(self, event: Event, articles: list[StoredArticle]) -> ResearchBrief:
        pack = self.evidence_repository.save(self.gatherer.gather(event, articles))
        try:
            brief = self.analyst.analyze(event, pack)
        except Exception as exc:
            if self.fallback is None:
                raise
            logger.warning(
                "Evidence-bound LLM research failed for event %s; using explicit fallback: %s",
                event.id,
                exc,
            )
            brief = self.fallback.analyze(event, pack)
            brief.research_mode = self.research_mode
            brief.generation_type = "fallback"
        brief.evidence_pack_id = pack.id
        return brief
