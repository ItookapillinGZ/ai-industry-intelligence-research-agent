from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from app.evaluation.reporter import EvaluationReportGenerator
from app.storage.evaluation_repository import EvaluationRepository
from app.storage.research_repository import ResearchRepository


class ResearchComparisonReportGenerator:
    MODES = ("deterministic", "single_source_llm", "multi_source_llm")

    def __init__(
        self,
        research_repository: ResearchRepository,
        evaluation_repository: EvaluationRepository,
        reports_dir: Path,
    ) -> None:
        self.research_repository = research_repository
        self.evaluation_repository = evaluation_repository
        self.reports_dir = reports_dir

    def generate(self, top_k: int = 10) -> Path:
        now = datetime.now(timezone.utc)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        path = self.reports_dir / f"research_comparison_{now.strftime('%Y%m%d_%H%M%S')}.md"
        evaluations = self.evaluation_repository.list_with_context()
        lines = [
            "# Phase 2.5 Research Quality Comparison",
            "",
            f"- Generated at: {now.replace(microsecond=0).isoformat()}",
            f"- Evaluation target: Top {top_k} events",
            "- Live LLM results are counted only when generation_type is live.",
            "",
            "## Validation Status",
            "",
            "| Mode | Briefs | Generation states | Human evaluations |",
            "|---|---:|---|---:|",
        ]
        mode_items = {}
        for mode in self.MODES:
            items = self.research_repository.list_with_events(top_k, research_mode=mode)
            mode_items[mode] = items
            states = Counter(brief.generation_type for _event, brief in items)
            state_text = ", ".join(f"{key}={value}" for key, value in sorted(states.items())) or "none"
            evaluated = sum(1 for item in evaluations if item[2] == mode)
            lines.append(f"| {mode} | {len(items)} | {state_text} | {evaluated} |")

        lines.extend(
            [
                "",
                "## Average Human Scores",
                "",
                "| Mode | Factuality | Source coverage | Relevance | Insightfulness | Clarity |",
                "|---|---:|---:|---:|---:|---:|",
            ]
        )
        for mode in self.MODES:
            rows = [item[0] for item in evaluations if item[2] == mode]
            if not rows:
                lines.append(f"| {mode} | pending | pending | pending | pending | pending |")
                continue
            averages = [
                sum(getattr(row, dimension) for row in rows) / len(rows)
                for dimension in EvaluationReportGenerator.DIMENSIONS
            ]
            lines.append(
                f"| {mode} | {averages[0]:.2f} | {averages[1]:.2f} | "
                f"{averages[2]:.2f} | {averages[3]:.2f} | {averages[4]:.2f} |"
            )

        lines.extend(["", "## Source Coverage", ""])
        lines.extend(
            [
                "| Mode | Avg sources per brief | Avg independent sources | Official + independent |",
                "|---|---:|---:|---:|",
            ]
        )
        for mode in self.MODES:
            briefs = [brief for _event, brief in mode_items[mode]]
            if not briefs:
                lines.append(f"| {mode} | 0.00 | 0.00 | 0 |")
                continue
            avg_sources = sum(len(brief.sources) for brief in briefs) / len(briefs)
            independent = [
                len({source.url for source in brief.sources if source.source_type == "independent"})
                for brief in briefs
            ]
            both = sum(
                1
                for brief in briefs
                if any(source.source_type == "official" for source in brief.sources)
                and any(source.source_type == "independent" for source in brief.sources)
            )
            lines.append(
                f"| {mode} | {avg_sources:.2f} | {sum(independent) / len(briefs):.2f} | {both} |"
            )

        live_count = sum(
            1
            for items in mode_items.values()
            for _event, brief in items
            if brief.generation_type == "live"
        )
        lines.extend(
            [
                "",
                "## Interpretation",
                "",
                (
                    "Live LLM validation is blocked by missing API key."
                    if live_count == 0
                    else f"Live LLM validation includes {live_count} brief(s)."
                ),
                "No score is inferred for missing human evaluations.",
                "",
            ]
        )
        path.write_text("\n".join(lines), encoding="utf-8")
        return path
