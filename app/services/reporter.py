from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from app.models import StoredArticle
from app.storage.article_repository import ArticleRepository


def _escape_markdown(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


class MarkdownReporter:
    def __init__(self, repository: ArticleRepository, reports_dir: Path) -> None:
        self.repository = repository
        self.reports_dir = reports_dir

    def generate(self, limit: int) -> Path:
        articles = self.repository.list_for_report(limit)
        generated_at = datetime.now(timezone.utc)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        path = self.reports_dir / f"ai_intelligence_{generated_at.strftime('%Y%m%d_%H%M%S')}.md"
        path.write_text(self._render(articles, generated_at), encoding="utf-8")
        return path

    def _render(self, articles: list[StoredArticle], generated_at: datetime) -> str:
        lines = [
            "# AI Industry Intelligence Report",
            "",
            f"- Generated at: {generated_at.replace(microsecond=0).isoformat()}",
            f"- Articles: {len(articles)}",
            "- Pipeline: Source → Collector → Normalize → Deduplicate → Classify → Score → Summarize → Markdown Report",
            "",
        ]
        if not articles:
            lines.extend(["_No processed articles are available yet._", ""])
            return "\n".join(lines)

        lines.extend(
            [
                "## Executive Index",
                "",
                "| Score | Category | Article | Source |",
                "|---:|---|---|---|",
            ]
        )
        for article in articles:
            score = article.importance_score if article.importance_score is not None else 0
            lines.append(
                f"| {score:.1f} | {_escape_markdown(article.category or 'Other')} | "
                f"[{_escape_markdown(article.title)}]({article.url}) | {_escape_markdown(article.source)} |"
            )

        grouped: dict[str, list[StoredArticle]] = defaultdict(list)
        for article in articles:
            grouped[article.category or "Other"].append(article)

        for category in sorted(grouped):
            lines.extend(["", f"## {category}", ""])
            for article in grouped[category]:
                score = article.importance_score if article.importance_score is not None else 0
                date = article.published_at or article.collected_at
                lines.extend(
                    [
                        f"### [{article.title}]({article.url})",
                        "",
                        f"- **Importance:** {score:.1f}/10",
                        f"- **Source:** {article.source}",
                        f"- **Published:** {date}",
                        f"- **Tags:** {', '.join(article.tags) if article.tags else '—'}",
                        "",
                        article.summary or "_No summary available._",
                        "",
                    ]
                )
        return "\n".join(lines)

