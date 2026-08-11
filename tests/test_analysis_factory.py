from __future__ import annotations

from app.analysis.factory import build_analysis_components
from app.analysis.fallback import ExtractiveSummarizer, KeywordClassifier, RuleBasedImportanceScorer


def test_missing_api_key_uses_local_fallback(monkeypatch) -> None:
    monkeypatch.setenv("AI_INTEL_LLM_PROVIDER", "openai_compatible")
    monkeypatch.delenv("AI_INTEL_LLM_API_KEY", raising=False)
    components = build_analysis_components()
    assert components.provider_name == "local-fallback"
    assert isinstance(components.classifier, KeywordClassifier)
    assert isinstance(components.scorer, RuleBasedImportanceScorer)
    assert isinstance(components.summarizer, ExtractiveSummarizer)
