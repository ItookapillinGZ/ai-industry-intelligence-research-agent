from __future__ import annotations

import re

from app.models import ClassificationResult, StoredArticle
from app.analysis.taxonomy import classify_text


def _analysis_content(article: StoredArticle) -> str:
    return article.content or article.raw_text


def _article_text(article: StoredArticle) -> str:
    return f"{article.title} {_analysis_content(article)}".casefold()


class KeywordClassifier:
    def classify(self, article: StoredArticle) -> ClassificationResult:
        category, tags = classify_text(article.title, _analysis_content(article))
        return ClassificationResult(category=category, tags=tags)


class RuleBasedImportanceScorer:
    HIGH_SIGNAL_TERMS = (
        "release",
        "launch",
        "benchmark",
        "open source",
        "funding",
        "acquisition",
        "research",
        "model",
        "发布",
        "开源",
    )

    def score(self, article: StoredArticle, classification: ClassificationResult) -> float:
        text = _article_text(article)
        score = 4.0
        score += min(3.0, sum(0.6 for term in self.HIGH_SIGNAL_TERMS if term in text))
        if len(_analysis_content(article)) >= 500:
            score += 0.5
        if classification.category != "Other":
            score += 0.5
        return round(min(score, 10.0), 1)


class ExtractiveSummarizer:
    def __init__(self, max_length: int = 360) -> None:
        self.max_length = max_length

    def summarize(self, article: StoredArticle) -> str:
        text = re.sub(r"\s+", " ", _analysis_content(article)).strip()
        if not text:
            return article.title
        sentences = re.split(r"(?<=[.!?。！？])\s+", text)
        summary = " ".join(sentences[:2]).strip()
        if len(summary) <= self.max_length:
            return summary
        shortened = summary[: self.max_length - 1].rsplit(" ", 1)[0].rstrip()
        return (shortened or summary[: self.max_length - 1]).rstrip() + "…"

