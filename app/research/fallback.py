from __future__ import annotations

import re

from app.models import (
    EvidenceReference,
    Event,
    ResearchBrief,
    ResearchSource,
    StoredArticle,
)


def _first_sentence(value: str, limit: int = 320) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    if not text:
        return ""
    sentence = re.split(r"(?<=[.!?。！？])\s+", text, maxsplit=1)[0]
    return sentence if len(sentence) <= limit else sentence[: limit - 1].rstrip() + "…"


class DeterministicResearchAgent:
    provider_name = "local-research-fallback"

    WHY = {
        "AI Agent": "This may affect how AI systems execute multi-step work and how products delegate tasks.",
        "AI Coding": "This may change developer workflows, software delivery speed, or code evaluation practices.",
        "LLM": "This may affect model capability, cost, availability, or the competitive model landscape.",
        "AIGC": "This may change the capabilities or economics of generative content production.",
        "AI Product": "This may influence AI product adoption, distribution, or user expectations.",
        "Other": "The available evidence indicates an AI industry development, but its broader significance is not yet clear.",
    }

    def research(self, event: Event, articles: list[StoredArticle]) -> ResearchBrief:
        if not articles:
            raise ValueError("Research requires at least one linked article")
        ranked = sorted(articles, key=lambda item: item.importance_score or 0, reverse=True)
        sources = [
            ResearchSource(article_id=a.id, title=a.title, source=a.source, url=a.url)
            for a in ranked
        ]
        key_facts: list[dict[str, object]] = []
        evidence: list[EvidenceReference] = []
        for article in ranked[:4]:
            text = article.content or article.summary or article.raw_text or article.title
            statement = _first_sentence(text) or article.title
            key_facts.append(
                {
                    "statement": statement,
                    "type": "reported_fact",
                    "source_article_ids": [article.id],
                }
            )
            evidence.append(
                EvidenceReference(
                    claim=statement,
                    article_id=article.id,
                    url=article.url,
                    evidence_text=statement,
                    evidence_type="paraphrase",
                )
            )

        what_happened = key_facts[0]["statement"]
        source_count = len({article.source for article in articles})
        full_content_count = sum(1 for article in articles if article.content_status == "fetched")
        uncertainties: list[str] = []
        if source_count == 1:
            uncertainties.append("Only one independent source is available for this event.")
        if full_content_count < len(articles):
            uncertainties.append(
                f"Full text was available for {full_content_count} of {len(articles)} linked articles."
            )
        if not uncertainties:
            uncertainties.append("No explicit source conflict was detected; independent verification is still limited.")

        if event.category == "AIGC":
            ugc = (
                "Medium relevance: the development may affect creator tools, content production workflows, "
                "or the supply and cost of generated media. This is an inference from the event category."
            )
        else:
            ugc = (
                "Low relevance / limited direct impact: the supplied evidence does not establish a direct "
                "effect on creators, short-video production, community content, or the UGC ecosystem."
            )

        confidence = min(
            0.85,
            0.3 + min(source_count, 3) * 0.1 + 0.15 * full_content_count / len(articles),
        )
        tags = list(dict.fromkeys([event.category, *(tag for article in articles for tag in article.tags)]))[:12]
        executive = _first_sentence(str(what_happened), 420)
        return ResearchBrief(
            event_id=event.id,
            headline=event.title,
            executive_summary=executive,
            what_happened=str(what_happened),
            key_facts=key_facts,
            background=(
                f"The event is represented by {len(articles)} linked article(s) from "
                f"{source_count} independent source(s). The supplied evidence does not provide "
                "enough verified historical context for stronger background claims."
            ),
            why_it_matters=self.WHY.get(event.category, self.WHY["Other"]),
            industry_impact=(
                "Potential industry impact remains provisional. Monitor follow-up evidence on adoption, "
                "availability, performance, pricing, and competitor response."
            ),
            ugc_relevance=ugc,
            evidence=evidence,
            sources=sources,
            uncertainties=uncertainties,
            claim_confidence=round(confidence, 2),
            verification_level="single_first_party",
            tags=tags,
            provider_name=self.provider_name,
        )


# Phase 2.5 implementation keeps the legacy class above as migration context.
from app.research.evidence_analyst import (
    DeterministicEvidenceAnalyst as DeterministicResearchAgent,
)
