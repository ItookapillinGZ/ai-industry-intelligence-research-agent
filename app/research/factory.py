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

