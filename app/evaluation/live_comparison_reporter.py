from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from app.models import ResearchBrief
from app.storage.research_repository import ResearchRepository


def _one_line(value: str) -> str:
    return " ".join(value.split())


def _usage_text(usage: dict[str, int | float]) -> str:
    if not usage:
        return "not returned"
    return ", ".join(f"{key}={value}" for key, value in sorted(usage.items()))


class LiveResearchComparisonReportGenerator:
    MODE_SPECS = (
        ("deterministic", "deterministic", "deterministic"),
        ("live_single_source_llm", "single_source_llm", "live"),
        ("live_multi_source_llm", "multi_source_llm", "live"),
    )

    def __init__(self, repository: ResearchRepository, reports_dir: Path) -> None:
        self.repository = repository
        self.reports_dir = reports_dir

    def generate(self, top_k: int = 5) -> tuple[Path, Path]:
        now = datetime.now(timezone.utc)
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        report_path = self.reports_dir / f"live_research_comparison_{timestamp}.md"
        dataset_path = self.reports_dir / f"live_research_comparison_{timestamp}.json"
        grouped: dict[int, dict[str, object]] = {}
        mode_counts: dict[str, int] = {}
        for label, mode, generation_type in self.MODE_SPECS:
            rows = self.repository.list_with_events(
                top_k, research_mode=mode, generation_type=generation_type
            )
            mode_counts[label] = len(rows)
            for event, brief in rows:
                entry = grouped.setdefault(event.id, {"event": event, "results": {}})
                entry["results"][label] = brief
        ordered = sorted(
            grouped.values(),
            key=lambda entry: (-entry["event"].importance_score, entry["event"].id),
        )[:top_k]
        excluded = {
            mode: self.repository.count(mode, "fallback")
            for mode in ("single_source_llm", "multi_source_llm")
        }
        payload = {
            "phase": "2.6 Live LLM Research Validation",
            "generated_at": now.replace(microsecond=0).isoformat(),
            "top_k": top_k,
            "human_quality_scores": "pending",
            "selection_rule": {
                "deterministic": "generation_type=deterministic",
                "live_single_source_llm": "research_mode=single_source_llm and generation_type=live",
                "live_multi_source_llm": "research_mode=multi_source_llm and generation_type=live",
            },
            "excluded_historical_fallbacks": excluded,
            "events": [self._dataset_event(entry) for entry in ordered],
        }
        dataset_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        report_path.write_text(
            self._render(now, top_k, ordered, mode_counts, excluded), encoding="utf-8"
        )
        return report_path, dataset_path

    def _dataset_event(self, entry: dict[str, object]) -> dict[str, object]:
        event = entry["event"]
        results = entry["results"]
        rows = []
        for label, mode, generation_type in self.MODE_SPECS:
            brief = results.get(label)
            if brief is None:
                rows.append({
                    "label": label,
                    "research_mode": mode,
                    "generation_type": generation_type,
                    "status": "missing",
                    "human_quality_score": "pending",
                })
            else:
                rows.append(self._dataset_result(label, brief))
        return {
            "event_id": event.id,
            "event": event.title,
            "importance_score": event.importance_score,
            "results": rows,
        }

    @staticmethod
    def _dataset_result(label: str, brief: ResearchBrief) -> dict[str, object]:
        urls = {source.url for source in brief.sources}
        official = {
            source.url for source in brief.sources if source.source_type == "official"
        }
        independent = {
            source.url for source in brief.sources if source.source_type == "independent_media"
        }
        community = {
            source.url for source in brief.sources if source.source_type == "community"
        }
        research = {
            source.url for source in brief.sources if source.source_type == "research"
        }
        return {
            "label": label,
            "research_brief_id": brief.id,
            "research_mode": brief.research_mode,
            "generation_type": brief.generation_type,
            "status": "live_llm" if brief.generation_type == "live" else "deterministic_baseline",
            "provider": brief.provider_name,
            "model": brief.model_name,
            "total_source_count": len(urls),
            "official_source_count": len(official),
            "independent_source_count": len(independent),
            "community_source_count": len(community),
            "research_source_count": len(research),
            "independent_source_coverage": (
                "sufficient" if independent else "insufficient"
            ),
            "claim_confidence": brief.claim_confidence,
            "verification_level": brief.verification_level,
            "uncertainties": brief.uncertainties,
            "human_quality_score": "pending",
            "usage": brief.usage,
            "output": {
                "headline": brief.headline,
                "executive_summary": brief.executive_summary,
                "what_happened": brief.what_happened,
                "key_facts": brief.key_facts,
                "background": brief.background,
                "why_it_matters": brief.why_it_matters,
                "industry_impact": brief.industry_impact,
                "ugc_relevance": asdict(brief.ugc_relevance),
            },
            "sources": [asdict(source) for source in brief.sources],
            "evidence": [asdict(item) for item in brief.evidence],
        }

    def _render(
        self,
        now: datetime,
        top_k: int,
        ordered: list[dict[str, object]],
        mode_counts: dict[str, int],
        excluded: dict[str, int],
    ) -> str:
        lines = [
            "# Phase 2.6 Live Research Comparison",
            "",
            f"- Generated at: {now.replace(microsecond=0).isoformat()}",
            f"- Scope: Top {top_k} ranked events",
            "- Human quality scoring: **pending**",
            "- No claim is made that LLM output is better than the deterministic baseline.",
            "- Historical fallback rows excluded: "
            + ", ".join(f"{key}={value}" for key, value in excluded.items()),
            "",
            "## Validation Status",
            "",
            "| Result class | Required generation type | Included briefs |",
            "|---|---|---:|",
        ]
        for label, _mode, generation_type in self.MODE_SPECS:
            lines.append(f"| {label} | {generation_type} | {mode_counts[label]} |")
        lines.extend([
            "",
            "## Source Coverage and Verification",
            "",
            "| Event | Mode | Provider / model | Total | Official | Independent | Community | Research | Claim confidence | Verification level | Uncertainties |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|---|---|",
        ])
        for entry in ordered:
            event = entry["event"]
            results = entry["results"]
            for label, _mode, _generation_type in self.MODE_SPECS:
                brief = results.get(label)
                if brief is None:
                    lines.append(
                        f"| {_one_line(event.title)} | {label} | missing | 0 | 0 | 0 | 0 | 0 | - | missing result |"
                    )
                    continue
                source_urls = {source.url for source in brief.sources}
                official = {
                    source.url for source in brief.sources
                    if source.source_type == "official"
                }
                independent = {
                    source.url for source in brief.sources
                    if source.source_type == "independent_media"
                }
                community = {
                    source.url for source in brief.sources
                    if source.source_type == "community"
                }
                research = {
                    source.url for source in brief.sources
                    if source.source_type == "research"
                }
                uncertainties = "<br>".join(
                    _one_line(item) for item in brief.uncertainties
                ) or "none stated"
                lines.append(
                    f"| {_one_line(event.title)} | {label} | "
                    f"{brief.provider_name} / {brief.model_name or 'not returned'} | "
                    f"{len(source_urls)} | {len(official)} | {len(independent)} | "
                    f"{len(community)} | {len(research)} | "
                    f"{brief.claim_confidence:.2f} | {brief.verification_level} | {uncertainties} |"
                )
        lines.extend(["", "## Output Comparison", ""])
        for entry in ordered:
            event = entry["event"]
            results = entry["results"]
            lines.extend([f"### Event {event.id}: {event.title}", ""])
            for label, _mode, _generation_type in self.MODE_SPECS:
                brief = results.get(label)
                lines.extend([f"#### {label}", ""])
                if brief is None:
                    lines.extend(["_Missing result._", ""])
                    continue
                lines.extend([
                    f"- **Status:** {brief.research_mode} / {brief.generation_type}",
                    f"- **Provider/model:** {brief.provider_name} / {brief.model_name or 'not returned'}",
                    f"- **Claim confidence:** {brief.claim_confidence:.2f}",
                    f"- **Verification level:** {brief.verification_level}",
                    f"- **Usage:** {_usage_text(brief.usage)}",
                    f"- **Headline:** {_one_line(brief.headline)}",
                    f"- **Executive summary:** {_one_line(brief.executive_summary)}",
                    f"- **What happened:** {_one_line(brief.what_happened)}",
                    f"- **Why it matters:** {_one_line(brief.why_it_matters)}",
                    f"- **Industry impact:** {_one_line(brief.industry_impact)}",
                    "- **UGC relevance:** "
                    f"{brief.ugc_relevance.level}/{brief.ugc_relevance.directness}; "
                    f"{_one_line(brief.ugc_relevance.reason)}; areas={brief.ugc_relevance.affected_areas}",
                    "- **Key facts:**",
                ])
                for fact in brief.key_facts:
                    lines.append(
                        f"  - [{fact.get('type')}] {_one_line(str(fact.get('statement', '')))} "
                        f"(sources={fact.get('source_ids', [])})"
                    )
                lines.append("- **Uncertainties:**")
                lines.extend(f"  - {_one_line(item)}" for item in brief.uncertainties)
                lines.append("- **Sources:**")
                lines.extend(
                    f"  - {source.source_id} [{_one_line(source.title)}]({source.url}) "
                    f"({source.source_type})"
                    for source in brief.sources
                )
                lines.append("")
        return "\n".join(lines)
