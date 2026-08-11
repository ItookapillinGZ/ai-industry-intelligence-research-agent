from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app.storage.event_repository import EventRepository


class RankingAuditReportGenerator:
    DIMENSIONS = (
        "novelty",
        "industry_magnitude",
        "source_authority",
        "source_diversity",
        "ecosystem_impact",
        "developer_impact",
        "creator_impact",
        "recency",
    )

    def __init__(self, repository: EventRepository, reports_dir: Path) -> None:
        self.repository = repository
        self.reports_dir = reports_dir

    def generate(self, top_k: int = 10) -> Path:
        events = self.repository.list_events(limit=top_k)
        now = datetime.now(timezone.utc)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        path = self.reports_dir / f"ranking_audit_{now.strftime('%Y%m%d_%H%M%S')}.md"
        lines = [
            "# Phase 2.5 Importance Ranking Audit",
            "",
            f"- Generated at: {now.replace(microsecond=0).isoformat()}",
            f"- Events audited: {len(events)}",
            "- Total score is the bounded sum of eight independently named dimensions.",
            "- A single official case study can score source authority, but not source diversity.",
            "",
            "## Top Events",
            "",
            "| Rank | Event | Category | Total | Novelty | Magnitude | Authority | Diversity | Ecosystem | Developer | Creator | Recency |",
            "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for index, event in enumerate(events, 1):
            factors = event.importance_factors
            title = event.title.replace("|", "\\|")
            lines.append(
                f"| {index} | {title} | {event.category} | {event.importance_score:.2f} | "
                f"{factors.get('novelty', 0):.2f} | "
                f"{factors.get('industry_magnitude', 0):.2f} | "
                f"{factors.get('source_authority', 0):.2f} | "
                f"{factors.get('source_diversity', 0):.2f} | "
                f"{factors.get('ecosystem_impact', 0):.2f} | "
                f"{factors.get('developer_impact', 0):.2f} | "
                f"{factors.get('creator_impact', 0):.2f} | "
                f"{factors.get('recency', 0):.2f} |"
            )
        lines.extend(
            [
                "",
                "## Interpretation Guardrails",
                "",
                "- No article-specific title or publisher receives a hard-coded bonus.",
                "- Promotional first-party evidence does not create source diversity.",
                "- Creator impact is scored only when direct creator/content signals exist.",
                "- Recency cannot compensate for low novelty and low industry magnitude by itself.",
                "",
            ]
        )
        path.write_text("\n".join(lines), encoding="utf-8")
        return path
