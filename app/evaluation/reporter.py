from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app.storage.evaluation_repository import EvaluationRepository


class EvaluationReportGenerator:
    DIMENSIONS = ("factuality", "source_coverage", "relevance", "insightfulness", "clarity")

    def __init__(self, repository: EvaluationRepository, reports_dir: Path) -> None:
        self.repository = repository
        self.reports_dir = reports_dir

    def generate(self) -> Path:
        evaluations = self.repository.list_with_headlines()
        now = datetime.now(timezone.utc)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        path = self.reports_dir / f"evaluation_{now.strftime('%Y%m%d_%H%M%S')}.md"
        lines = [
            "# ResearchBrief Evaluation Summary",
            "",
            f"- Generated at: {now.replace(microsecond=0).isoformat()}",
            f"- Evaluations: {len(evaluations)}",
            "",
        ]
        if not evaluations:
            lines.extend(["_No evaluation results are available._", ""])
        else:
            lines.extend(["## Average Scores", "", "| Dimension | Average |", "|---|---:|"])
            for dimension in self.DIMENSIONS:
                average = sum(getattr(item, dimension) for item, _ in evaluations) / len(evaluations)
                lines.append(f"| {dimension} | {average:.2f}/5 |")
            lines.extend(
                [
                    "",
                    "## Individual Evaluations",
                    "",
                    "| Brief | Evaluator | Factuality | Coverage | Relevance | Insight | Clarity |",
                    "|---|---|---:|---:|---:|---:|---:|",
                ]
            )
            for item, headline in evaluations:
                safe_headline = headline.replace("|", "\\|")
                lines.append(
                    f"| {safe_headline} | {item.evaluator} | {item.factuality} | "
                    f"{item.source_coverage} | {item.relevance} | {item.insightfulness} | {item.clarity} |"
                )
                if item.notes:
                    lines.extend(["", f"- **{safe_headline}:** {item.notes}"])
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

