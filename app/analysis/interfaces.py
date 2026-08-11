from __future__ import annotations

from typing import Protocol

from app.models import ClassificationResult, StoredArticle


class Classifier(Protocol):
    def classify(self, article: StoredArticle) -> ClassificationResult: ...


class ImportanceScorer(Protocol):
    def score(self, article: StoredArticle, classification: ClassificationResult) -> float: ...


class Summarizer(Protocol):
    def summarize(self, article: StoredArticle) -> str: ...


class LLMProvider(Protocol):
    name: str

    def generate(self, system_prompt: str, user_prompt: str) -> str: ...


class AnalysisComponents:
    def __init__(
        self,
        classifier: Classifier,
        scorer: ImportanceScorer,
        summarizer: Summarizer,
        provider_name: str,
    ) -> None:
        self.classifier = classifier
        self.scorer = scorer
        self.summarizer = summarizer
        self.provider_name = provider_name

