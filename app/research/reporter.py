from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app.models import ResearchBrief
from app.storage.research_repository import ResearchRepository


def _clean(value: str) -> str:
    return value.replace("\n", " ").strip()


class ResearchReportGenerator:
    def __init__(self, repository: ResearchRepository, reports_dir: Path) -> None:
        self.repository = repository
        self.reports_dir = reports_dir

    def generate(
        self,
        limit: int,
        research_mode: str | None = None,
        generation_type: str | None = None,
    ) -> Path:
        items = self.repository.list_with_events(limit, research_mode, generation_type)
        now = datetime.now(timezone.utc)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        mode_label = research_mode or "all_modes"
        generation_label = f"_{generation_type}" if generation_type else ""
        path = self.reports_dir / (
            f"research_{mode_label}{generation_label}_{now.strftime('%Y%m%d_%H%M%S')}.md"
        )
        lines = [
            "# AI Industry Intelligence Report",
            "",
            f"- Generated at: {now.replace(microsecond=0).isoformat()}",
            f"- Researched events: {len(items)}",
            "",
            "## Executive Summary",
            "",
        ]
        if not items:
            lines.extend(["_No ResearchBrief records are available._", ""])
        else:
            for index, (_event, brief) in enumerate(items, 1):
                lines.append(f"{index}. **{_clean(brief.headline)}** — {_clean(brief.executive_summary)}")
            lines.extend(["", "## Top Events", ""])
            for index, (event, brief) in enumerate(items, 1):
                lines.extend(self._render_event(index, event.importance_score, event.category, brief))
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    def _render_event(
        self,
        index: int,
        importance: float,
        category: str,
        brief: ResearchBrief,
    ) -> list[str]:
        lines = [
            f"### {index}. {_clean(brief.headline)}",
            "",
            f"- **Importance:** {importance:.2f}/10",
            f"- **Claim confidence:** {brief.claim_confidence:.2f}",
            f"- **Verification level:** {brief.verification_level}",
            f"- **Research mode:** {brief.research_mode} ({brief.generation_type})",
            f"- **Provider:** {brief.provider_name}",
            f"- **Model:** {brief.model_name or 'not returned'}",
            f"- **Category:** {category}",
            "",
            "#### What happened",
            "",
            brief.what_happened,
            "",
            "#### Key facts",
            "",
        ]
        for fact in brief.key_facts:
            kind = fact.get("type", "reported_fact")
            ids = fact.get("source_ids", fact.get("source_article_ids", []))
            source_ids = ", ".join(str(item) for item in ids)
            lines.append(f"- **{kind}:** {fact.get('statement', '')} _(articles: {source_ids or '—'})_")
        lines.extend(
            [
                "",
                "#### Background",
                "",
                brief.background,
                "",
                "#### Why it matters",
                "",
                brief.why_it_matters,
                "",
                "#### Industry impact",
                "",
                brief.industry_impact,
                "",
                "#### UGC relevance",
                "",
                f"- **Level:** {brief.ugc_relevance.level}",
                f"- **Directness:** {brief.ugc_relevance.directness}",
                f"- **Reason:** {brief.ugc_relevance.reason}",
                f"- **Affected areas:** {', '.join(brief.ugc_relevance.affected_areas) or 'none'}",
                "",
                "#### Uncertainties",
                "",
            ]
        )
        lines.extend(f"- {item}" for item in brief.uncertainties)
        lines.extend(["", "#### Evidence references", ""])
        for item in brief.evidence:
            lines.append(
                f"- **{item.source_id}:** {_clean(item.claim)} -- [source]({item.url}) "
                f"_({item.evidence_type})_"
            )
            if item.evidence_type == "verbatim_quote":
                lines.extend(["", f"> {_clean(item.evidence_text)}", ""])
            else:
                lines.append(f"  - Paraphrase: {_clean(item.evidence_text)}")
        lines.extend(["", "#### Sources", ""])
        for source in brief.sources:
            lines.append(f"- [{_clean(source.title)}]({source.url}) — {source.source}")
        lines.append("")
        return lines

