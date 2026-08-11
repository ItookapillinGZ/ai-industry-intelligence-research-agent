from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from app.storage.evaluation_repository import EvaluationRepository


class EvaluationReportGenerator:
    DIMENSIONS = ("factuality", "source_coverage", "relevance", "insightfulness", "clarity")
    MODE_ORDER = ("deterministic", "single_source_llm", "multi_source_llm")
    PILOT_LIMITATION = (
        "This is a small human-reviewed pilot evaluation over 5 events, "
        "not a statistically powered benchmark."
    )

    def __init__(self, repository: EvaluationRepository, reports_dir: Path) -> None:
        self.repository = repository
        self.reports_dir = reports_dir

    def generate(self) -> Path:
        evaluations = self.repository.list_with_context()
        now = datetime.now(timezone.utc)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        path = self.reports_dir / f"evaluation_{now.strftime('%Y%m%d_%H%M%S')}.md"
        lines = [
            "# ResearchBrief Human Evaluation Summary",
            "",
            f"- Generated at: {now.replace(microsecond=0).isoformat()}",
            f"- Evaluations: {len(evaluations)}",
            "- Reviewer type: human/manual",
            "",
            self.PILOT_LIMITATION,
            "",
        ]
        if not evaluations:
            lines.extend(["_No evaluation results are available._", ""])
        else:
            lines.extend(["## Average Scores", "", "| Dimension | Average |", "|---|---:|"])
            for dimension in self.DIMENSIONS:
                average = sum(getattr(item, dimension) for item, *_ in evaluations) / len(evaluations)
                lines.append(f"| {dimension} | {average:.2f}/5 |")

            grouped = defaultdict(list)
            for item, _headline, mode, _generation_type, _event_id in evaluations:
                grouped[mode].append(item)
            lines.extend(
                [
                    "",
                    "## Mode Averages",
                    "",
                    "| Mode | Briefs | Overall average | Factuality | Coverage | Relevance | Insight | Clarity |",
                    "|---|---:|---:|---:|---:|---:|---:|---:|",
                ]
            )
            for mode in self.MODE_ORDER:
                items = grouped.get(mode, [])
                if not items:
                    continue
                dimension_averages = [
                    sum(getattr(item, dimension) for item in items) / len(items)
                    for dimension in self.DIMENSIONS
                ]
                overall = sum(dimension_averages) / len(dimension_averages)
                values = " | ".join(f"{value:.2f}" for value in dimension_averages)
                lines.append(f"| {mode} | {len(items)} | {overall:.2f}/5 | {values} |")

            lines.extend(
                [
                    "",
                    "## Individual Evaluations",
                    "",
                    "| Event | Mode | Evaluator | Factuality | Coverage | Relevance | Insight | Clarity | Evaluated at |",
                    "|---|---|---|---:|---:|---:|---:|---:|---|",
                ]
            )
            for item, headline, mode, _generation_type, _event_id in evaluations:
                safe_headline = headline.replace("|", "\\|")
                lines.append(
                    f"| {safe_headline} | {mode} | {item.evaluator} | {item.factuality} | "
                    f"{item.source_coverage} | {item.relevance} | {item.insightfulness} | "
                    f"{item.clarity} | {item.created_at or 'unknown'} |"
                )
                if item.notes:
                    lines.extend(["", f"- **{safe_headline} ({mode}):** {item.notes}"])
        path.write_text("\n".join(lines), encoding="utf-8")
        return path
