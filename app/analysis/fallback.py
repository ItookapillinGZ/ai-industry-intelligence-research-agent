from __future__ import annotations

import re

from app.models import ClassificationResult, StoredArticle

CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "AI Agent": ("agent", "agentic", "multi-agent", "tool use", "智能体"),
    "AI Coding": ("coding", "code generation", "developer", "copilot", "ide", "编程"),
    "LLM": ("llm", "language model", "transformer", "reasoning model", "大模型"),
    "AIGC": ("image generation", "video generation", "diffusion", "text-to-video", "生成式"),
    "AI Product": ("launch", "product", "feature", "platform", "assistant", "发布"),
}


def _article_text(article: StoredArticle) -> str:
    return f"{article.title} {article.raw_text}".casefold()


class KeywordClassifier:
    def classify(self, article: StoredArticle) -> ClassificationResult:
        text = _article_text(article)
        category_scores = {
            category: sum(1 for keyword in keywords if keyword in text)
            for category, keywords in CATEGORY_KEYWORDS.items()
        }
        category = max(category_scores, key=category_scores.get)
        if category_scores[category] == 0:
            category = "Other"
        tags = [keyword for keyword in CATEGORY_KEYWORDS.get(category, ()) if keyword in text][:5]
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
        if article.raw_text and len(article.raw_text) >= 500:
            score += 0.5
        if classification.category != "Other":
            score += 0.5
        return round(min(score, 10.0), 1)


class ExtractiveSummarizer:
    def __init__(self, max_length: int = 360) -> None:
        self.max_length = max_length

    def summarize(self, article: StoredArticle) -> str:
        text = re.sub(r"\s+", " ", article.raw_text).strip()
        if not text:
            return article.title
        sentences = re.split(r"(?<=[.!?。！？])\s+", text)
        summary = " ".join(sentences[:2]).strip()
        if len(summary) <= self.max_length:
            return summary
        return summary[: self.max_length - 1].rsplit(" ", 1)[0].rstrip() + "…"

