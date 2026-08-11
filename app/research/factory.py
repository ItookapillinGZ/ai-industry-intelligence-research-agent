from __future__ import annotations

import logging
import os
from pathlib import Path

from app.analysis.llm import OpenAICompatibleProvider
from app.research.fallback import DeterministicResearchAgent
from app.research.interfaces import ResearchAgent
from app.research.llm_agent import LLMResearchAgent

logger = logging.getLogger(__name__)


class ResilientResearchAgent:
    def __init__(self, primary: ResearchAgent, fallback: ResearchAgent) -> None:
        self.primary = primary
        self.fallback = fallback
        self.provider_name = primary.provider_name

    def research(self, event, articles):
        try:
            return self.primary.research(event, articles)
        except Exception as exc:
            logger.warning("LLM research failed for event %s; using fallback: %s", event.id, exc)
            return self.fallback.research(event, articles)


def build_research_agent(prompts_dir: Path) -> ResearchAgent:
    fallback = DeterministicResearchAgent()
    choice = os.getenv("AI_INTEL_LLM_PROVIDER", "disabled").strip().lower()
    api_key = os.getenv("AI_INTEL_LLM_API_KEY", "").strip()
    if choice in {"", "disabled", "none", "fallback"} or not api_key:
        logger.info("Research LLM unavailable; using deterministic research fallback")
        return fallback
    if choice not in {"openai", "openai_compatible", "openai-compatible"}:
        logger.warning("Unknown research LLM provider '%s'; using fallback", choice)
        return fallback
    provider = OpenAICompatibleProvider(
        api_key=api_key,
        model=os.getenv("AI_INTEL_LLM_MODEL", "gpt-4.1-mini"),
        base_url=os.getenv("AI_INTEL_LLM_BASE_URL", "https://api.openai.com/v1"),
        timeout_seconds=int(os.getenv("AI_INTEL_LLM_TIMEOUT_SECONDS", "30")),
    )
    return ResilientResearchAgent(LLMResearchAgent(provider, prompts_dir), fallback)



def build_research_workflow(
    mode: str,
    prompts_dir: Path,
    database,
    search_timeout_seconds: int = 20,
):
    """Compose Phase 2.5 workflow without changing API-key safety rules."""
    from app.evidence.gatherers import (
        BingNewsSearchClient,
        SearchEvidenceGatherer,
        SeedEvidenceGatherer,
    )
    from app.research.evidence_analyst import (
        DeterministicEvidenceAnalyst,
        EvidenceBoundLLMAnalyst,
    )
    from app.research.workflow import ResearchWorkflow
    from app.storage.evidence_repository import EvidencePackRepository

    normalized_mode = mode.replace("-", "_")
    if normalized_mode not in {
        "deterministic",
        "single_source_llm",
        "multi_source_llm",
    }:
        raise ValueError(f"Unknown research mode: {mode}")

    if normalized_mode == "deterministic":
        return ResearchWorkflow(
            SeedEvidenceGatherer("deterministic"),
            DeterministicEvidenceAnalyst("deterministic"),
            EvidencePackRepository(database),
        )

    if normalized_mode == "single_source_llm":
        gatherer = SeedEvidenceGatherer("single_source_llm", max_sources=1)
    else:
        gatherer = SearchEvidenceGatherer(
            BingNewsSearchClient(timeout_seconds=search_timeout_seconds)
        )

    choice = os.getenv("AI_INTEL_LLM_PROVIDER", "disabled").strip().lower()
    api_key = os.getenv("AI_INTEL_LLM_API_KEY", "").strip()
    enabled = (
        choice not in {"", "disabled", "none", "fallback"}
        and bool(api_key)
        and choice in {"openai", "openai_compatible", "openai-compatible"}
    )
    if not enabled:
        logger.warning(
            "%s is blocked_missing_api_key; saved results will be marked fallback",
            normalized_mode,
        )
        return ResearchWorkflow(
            gatherer,
            DeterministicEvidenceAnalyst("fallback"),
            EvidencePackRepository(database),
        )

    provider = OpenAICompatibleProvider(
        api_key=api_key,
        model=os.getenv("AI_INTEL_LLM_MODEL", "gpt-4.1-mini"),
        base_url=os.getenv("AI_INTEL_LLM_BASE_URL", "https://api.openai.com/v1"),
        timeout_seconds=int(os.getenv("AI_INTEL_LLM_TIMEOUT_SECONDS", "30")),
    )
    return ResearchWorkflow(
        gatherer,
        EvidenceBoundLLMAnalyst(
            provider,
            prompts_dir,
            research_mode=normalized_mode,
            generation_type="live",
        ),
        EvidencePackRepository(database),
        fallback=DeterministicEvidenceAnalyst("fallback"),
    )
