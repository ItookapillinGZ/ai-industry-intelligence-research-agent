from __future__ import annotations

from pathlib import Path

from app.analysis.fallback import ExtractiveSummarizer, KeywordClassifier, RuleBasedImportanceScorer
from app.analysis.interfaces import AnalysisComponents
from app.models import ArticleInput
from app.services.normalizer import normalize_article
from app.services.processor import ArticleProcessor
from app.services.reporter import MarkdownReporter
from app.storage.article_repository import ArticleRepository


def test_fallback_processing_and_markdown_report(
    repository: ArticleRepository, tmp_path: Path
) -> None:
    article_id = repository.insert(
        normalize_article(
            ArticleInput(
                title="New open source coding agent released",
                url="https://example.com/coding-agent",
                source="Example AI",
                raw_text=(
                    "A new coding agent was released as open source. "
                    "It helps developers understand and modify code repositories."
                ),
                tags=["Example"],
            )
        )
    )
    components = AnalysisComponents(
        KeywordClassifier(),
        RuleBasedImportanceScorer(),
        ExtractiveSummarizer(),
        provider_name="local-fallback",
    )
    processed, failed = ArticleProcessor(repository, components).process(limit=10)
    assert (processed, failed) == (1, 0)

    stored = repository.list_for_report(10)[0]
    assert stored.id == article_id
    assert stored.category == "AI Coding"
    assert stored.summary
    assert stored.importance_score is not None

    path = MarkdownReporter(repository, tmp_path / "reports").generate(limit=10)
    report = path.read_text(encoding="utf-8")
    assert "# AI Industry Intelligence Report" in report
    assert "New open source coding agent released" in report
    assert "local-fallback" not in report


def test_empty_report_is_valid(repository: ArticleRepository, tmp_path: Path) -> None:
    path = MarkdownReporter(repository, tmp_path / "reports").generate(limit=10)
    assert "No processed articles" in path.read_text(encoding="utf-8")
