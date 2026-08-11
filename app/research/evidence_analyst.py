from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path

from app.analysis.interfaces import LLMProvider
from app.evidence.gatherers import SeedEvidenceGatherer
from app.models import (
    EvidencePack,
    EvidenceReference,
    Event,
    ResearchBrief,
    ResearchSource,
    StoredArticle,
    UGCRelevance,
)

UGC_AREAS = {
    "creator_tools",
    "content_creation",
    "short_video",
    "distribution",
    "community",
    "moderation",
}


class ResearchValidationError(ValueError):
    """Raised when model output violates the supplied Evidence Pack."""


class PromptLoader:
    def __init__(self, prompts_dir: Path) -> None:
        self.prompts_dir = prompts_dir

    def load(self, name: str) -> str:
        path = self.prompts_dir / name
        if not path.exists():
            raise FileNotFoundError(f"Research prompt not found: {path}")
        return path.read_text(encoding="utf-8")


def _json_object(value: str) -> dict:
    match = re.search(r"\{.*\}", value, flags=re.DOTALL)
    if not match:
        raise ResearchValidationError("Research response does not contain JSON")
    try:
        result = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise ResearchValidationError(f"Invalid research JSON: {exc}") from exc
    if not isinstance(result, dict):
        raise ResearchValidationError("Research JSON must be an object")
    return result


def _first_sentence(value: str, limit: int = 360) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    if not text:
        return ""
    sentence = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0]
    return sentence if len(sentence) <= limit else sentence[: limit - 1].rstrip() + "?"


def _ugc_from_evidence(pack: EvidencePack) -> UGCRelevance:
    text = " ".join(
        f"{item.title} {item.snippet} {item.content}" for item in pack.items
    ).casefold()
    signals = {
        "creator_tools": ("creator tool", "creative control", "editing tool"),
        "content_creation": (
            "content creation", "image generation", "video generation", "music generation",
        ),
        "short_video": ("short video", "tiktok", "reels", "shorts"),
        "distribution": ("distribution", "recommendation feed", "reach"),
        "community": ("community", "user-generated", "ugc"),
        "moderation": ("moderation", "content safety", "trust and safety"),
    }
    affected = [
        area for area, terms in signals.items() if any(term in text for term in terms)
    ]
    if not affected:
        return UGCRelevance(
            level="low",
            reason=(
                "The supplied evidence does not establish a direct effect on creators, "
                "content production, short video, distribution, communities, or moderation."
            ),
            affected_areas=[],
        )
    level = "high" if len(affected) >= 3 else "medium"
    return UGCRelevance(
        level=level,
        reason="The supplied evidence directly mentions workflows in the affected areas.",
        affected_areas=affected,
    )


class DeterministicEvidenceAnalyst:
    provider_name = "local-research-fallback"

    WHY = {
        "Foundation Model": "This may affect model capability, cost, availability, and competition.",
        "AI Agent": "This may affect how AI systems execute multi-step work and delegate tasks.",
        "AI Coding": "This may change developer workflows, delivery speed, or code quality practices.",
        "Multimodal / AIGC": "This may change generative media capabilities and production economics.",
        "AI Product": "This may influence product adoption, distribution, or user expectations.",
        "Enterprise Adoption": "This provides adoption evidence, but one customer case is not an industry-wide trend.",
        "Research": "This may change the evidence base for model capabilities or limitations.",
        "Open Source": "This may affect access, customization, transparency, and ecosystem competition.",
        "AI Safety": "This may affect risk management, evaluation practice, and responsible deployment.",
        "Cybersecurity": "This may affect defensive capability, misuse risk, and model security evaluation.",
        "Policy / Regulation": "This may change legal obligations, market access, or deployment constraints.",
        "Funding / Business": "This may affect company capacity, market structure, or competitive dynamics.",
        "Other": "Broader significance is not yet clear from the supplied evidence.",
    }

    def __init__(self, generation_type: str = "deterministic") -> None:
        self.generation_type = generation_type

    def research(self, event: Event, articles: list[StoredArticle]) -> ResearchBrief:
        pack = SeedEvidenceGatherer("deterministic").gather(event, articles)
        return self.analyze(event, pack)

    def analyze(self, event: Event, pack: EvidencePack) -> ResearchBrief:
        if not pack.items:
            raise ValueError("Research requires at least one evidence item")
        key_facts: list[dict[str, object]] = []
        evidence: list[EvidenceReference] = []
        for item in pack.items[:4]:
            statement = _first_sentence(item.content or item.snippet or item.title) or item.title
            key_facts.append(
                {
                    "statement": statement,
                    "type": "reported_fact",
                    "source_ids": [item.source_id],
                }
            )
            evidence.append(
                EvidenceReference(
                    claim=statement,
                    source_id=item.source_id,
                    article_id=item.article_id,
                    url=item.url,
                    excerpt=statement,
                )
            )

        source_count = len({item.source for item in pack.items})
        full_content_count = sum(1 for item in pack.items if item.content.strip())
        uncertainties = []
        if pack.coverage_status != "sufficient":
            uncertainties.append("Source coverage is insufficient: " + pack.coverage_note)
        if full_content_count < len(pack.items):
            uncertainties.append(
                f"Full text was available for {full_content_count} of {len(pack.items)} evidence items."
            )
        uncertainties.extend(pack.errors)
        if not uncertainties:
            uncertainties.append("No explicit source conflict was detected; further verification may still help.")

        confidence = min(
            0.88,
            0.3 + min(source_count, 3) * 0.1
            + 0.18 * full_content_count / len(pack.items),
        )
        first_fact = str(key_facts[0]["statement"])
        return ResearchBrief(
            event_id=event.id,
            headline=event.title,
            executive_summary=_first_sentence(first_fact, 420),
            what_happened=first_fact,
            key_facts=key_facts,
            background=(
                f"The Evidence Pack contains {len(pack.items)} item(s) from {source_count} source(s). "
                "The deterministic analyst does not add background facts beyond supplied evidence."
            ),
            why_it_matters=self.WHY.get(event.category, self.WHY["Other"]),
            industry_impact=(
                "Potential impact remains provisional. Monitor adoption, availability, performance, "
                "pricing, policy response, and independent corroboration."
            ),
            ugc_relevance=_ugc_from_evidence(pack),
            evidence=evidence,
            sources=[
                ResearchSource(
                    source_id=item.source_id,
                    article_id=item.article_id,
                    title=item.title,
                    source=item.source,
                    url=item.url,
                    source_type=item.source_type,
                )
                for item in pack.items
            ],
            uncertainties=uncertainties,
            confidence=round(confidence, 2),
            tags=[event.category],
            provider_name=self.provider_name,
            research_mode=pack.mode,
            generation_type=self.generation_type,
            evidence_pack_id=pack.id,
        )


class EvidenceBoundLLMAnalyst:
    def __init__(
        self,
        provider: LLMProvider,
        prompts_dir: Path,
        research_mode: str = "single_source_llm",
        generation_type: str = "live",
    ) -> None:
        self.provider = provider
        self.provider_name = provider.name
        self.prompts = PromptLoader(prompts_dir)
        self.research_mode = research_mode
        self.generation_type = generation_type

    def research(self, event: Event, articles: list[StoredArticle]) -> ResearchBrief:
        max_sources = 1 if self.research_mode == "single_source_llm" else None
        pack = SeedEvidenceGatherer(self.research_mode, max_sources).gather(event, articles)
        return self.analyze(event, pack)

    def analyze(self, event: Event, pack: EvidencePack) -> ResearchBrief:
        supplied = [asdict(item) for item in pack.items]
        template = self.prompts.load("research_event.txt")
        user_prompt = template.replace(
            "{{EVENT_JSON}}", json.dumps(asdict(event), ensure_ascii=False)
        ).replace("{{EVIDENCE_PACK_JSON}}", json.dumps(asdict(pack), ensure_ascii=False))
        user_prompt = user_prompt.replace("{{ARTICLES_JSON}}", json.dumps(supplied, ensure_ascii=False))
        response = self.provider.generate(self.prompts.load("research_system.txt"), user_prompt)
        return self._validate(_json_object(response), event, pack)

    def _validate(self, data: dict, event: Event, pack: EvidencePack) -> ResearchBrief:
        allowed = {item.source_id: item for item in pack.items}
        ids_by_article = {
            item.article_id: item.source_id for item in pack.items if item.article_id is not None
        }

        def required_text(key: str) -> str:
            value = data.get(key)
            if not isinstance(value, str) or not value.strip():
                raise ResearchValidationError(f"Missing non-empty field: {key}")
            return value.strip()

        raw_sources = data.get("sources")
        if not isinstance(raw_sources, list) or not raw_sources:
            raise ResearchValidationError("Research sources must be a non-empty list")
        sources = []
        for raw in raw_sources:
            if not isinstance(raw, dict):
                raise ResearchValidationError("Research sources must be objects")
            sid = str(raw.get("source_id", ""))
            item = allowed.get(sid)
            if item is None or raw.get("url") != item.url:
                raise ResearchValidationError("Research response contains an unknown source URL or ID")
            sources.append(
                ResearchSource(
                    source_id=sid, article_id=item.article_id, title=item.title,
                    source=item.source, url=item.url, source_type=item.source_type,
                )
            )

        evidence = []
        for raw in data.get("evidence", []):
            if not isinstance(raw, dict):
                raise ResearchValidationError("Evidence entries must be objects")
            sid = str(raw.get("source_id", ""))
            item = allowed.get(sid)
            if item is None or raw.get("url") != item.url:
                raise ResearchValidationError("Evidence refers to an unknown source")
            evidence.append(
                EvidenceReference(
                    claim=str(raw.get("claim", "")).strip(), source_id=sid,
                    article_id=item.article_id, url=item.url,
                    excerpt=str(raw.get("excerpt", "")).strip(),
                )
            )

        key_facts = data.get("key_facts")
        if not isinstance(key_facts, list):
            raise ResearchValidationError("key_facts must be a list")
        for fact in key_facts:
            if not isinstance(fact, dict) or fact.get("type") not in {"reported_fact", "inference"}:
                raise ResearchValidationError("Each key fact must distinguish reported_fact or inference")
            source_ids = fact.get("source_ids")
            if source_ids is None:
                source_ids = [ids_by_article.get(int(item), "") for item in fact.get("source_article_ids", [])]
                fact["source_ids"] = source_ids
            if any(str(sid) not in allowed for sid in source_ids):
                raise ResearchValidationError("A key fact refers to an unknown source")

        raw_ugc = data.get("ugc_relevance")
        if not isinstance(raw_ugc, dict):
            raise ResearchValidationError("ugc_relevance must be a structured object")
        level = str(raw_ugc.get("level", ""))
        areas = [str(item) for item in raw_ugc.get("affected_areas", [])]
        if level not in {"low", "medium", "high"} or any(area not in UGC_AREAS for area in areas):
            raise ResearchValidationError("Invalid UGC relevance level or affected area")
        reason = str(raw_ugc.get("reason", "")).strip()
        if not reason:
            raise ResearchValidationError("UGC relevance reason is required")
        confidence = float(data.get("confidence", -1))
        if not 0 <= confidence <= 1:
            raise ResearchValidationError("confidence must be between 0 and 1")

        return ResearchBrief(
            event_id=event.id, headline=required_text("headline"),
            executive_summary=required_text("executive_summary"),
            what_happened=required_text("what_happened"), key_facts=key_facts,
            background=required_text("background"), why_it_matters=required_text("why_it_matters"),
            industry_impact=required_text("industry_impact"),
            ugc_relevance=UGCRelevance(level=level, reason=reason, affected_areas=areas),
            evidence=evidence, sources=sources,
            uncertainties=[str(item) for item in data.get("uncertainties", [])],
            confidence=confidence, tags=[str(item) for item in data.get("tags", [])][:15],
            provider_name=self.provider_name, research_mode=pack.mode,
            generation_type=self.generation_type, evidence_pack_id=pack.id,
        )
