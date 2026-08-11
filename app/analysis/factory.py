from __future__ import annotations

import logging
import os
from collections.abc import Callable
from typing import TypeVar

from app.analysis.fallback import ExtractiveSummarizer, KeywordClassifier, RuleBasedImportanceScorer
from app.analysis.interfaces import AnalysisComponents, Classifier, ImportanceScorer, Summarizer
from app.analysis.llm import (
    LLMClassifier,
    LLMImportanceScorer,
    LLMSummarizer,
    OpenAICompatibleProvider,
)

logger = logging.getLogger(__name__)
T = TypeVar("T")


class _ResilientClassifier:
    def __init__(self, primary: Classifier, fallback: Classifier) -> None:
        self.primary = primary
        self.fallback = fallback

    def classify(self, article):
        try:
            return self.primary.classify(article)
        except Exception as exc:
            logger.warning("LLM classification failed for article %s; using fallback: %s", article.id, exc)
            return self.fallback.classify(article)


class _ResilientScorer:
    def __init__(self, primary: ImportanceScorer, fallback: ImportanceScorer) -> None:
        self.primary = primary
        self.fallback = fallback

    def score(self, article, classification):
        try:
            return self.primary.score(article, classification)
        except Exception as exc:
            logger.warning("LLM scoring failed for article %s; using fallback: %s", article.id, exc)
            return self.fallback.score(article, classification)


class _ResilientSummarizer:
    def __init__(self, primary: Summarizer, fallback: Summarizer) -> None:
        self.primary = primary
        self.fallback = fallback

    def summarize(self, article):
        try:
            return self.primary.summarize(article)
        except Exception as exc:
            logger.warning("LLM summarization failed for article %s; using fallback: %s", article.id, exc)
            return self.fallback.summarize(article)


def build_analysis_components() -> AnalysisComponents:
    fallback_classifier = KeywordClassifier()
    fallback_scorer = RuleBasedImportanceScorer()
    fallback_summarizer = ExtractiveSummarizer()

    provider_choice = os.getenv("AI_INTEL_LLM_PROVIDER", "disabled").strip().lower()
    api_key = os.getenv("AI_INTEL_LLM_API_KEY", "").strip()
    if provider_choice in {"", "disabled", "none", "fallback"} or not api_key:
        reason = "provider disabled" if provider_choice in {"", "disabled", "none", "fallback"} else "API key missing"
        logger.info("LLM unavailable (%s); using deterministic local analysis", reason)
        return AnalysisComponents(
            fallback_classifier,
            fallback_scorer,
            fallback_summarizer,
            provider_name="local-fallback",
        )

    if provider_choice not in {"openai", "openai_compatible", "openai-compatible"}:
        logger.warning("Unknown LLM provider '%s'; using deterministic local analysis", provider_choice)
        return AnalysisComponents(
            fallback_classifier,
            fallback_scorer,
            fallback_summarizer,
            provider_name="local-fallback",
        )

    provider = OpenAICompatibleProvider(
        api_key=api_key,
        model=os.getenv("AI_INTEL_LLM_MODEL", "gpt-4.1-mini"),
        base_url=os.getenv("AI_INTEL_LLM_BASE_URL", "https://api.openai.com/v1"),
        timeout_seconds=int(os.getenv("AI_INTEL_LLM_TIMEOUT_SECONDS", "30")),
    )
    logger.info("Using LLM provider %s", provider.name)
    return AnalysisComponents(
        _ResilientClassifier(LLMClassifier(provider), fallback_classifier),
        _ResilientScorer(LLMImportanceScorer(provider), fallback_scorer),
        _ResilientSummarizer(LLMSummarizer(provider), fallback_summarizer),
        provider_name=provider.name,
    )

