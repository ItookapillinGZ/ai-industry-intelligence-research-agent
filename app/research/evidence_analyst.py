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
EVIDENCE_TYPES = {"verbatim_quote", "paraphrase"}
VERIFICATION_LEVELS = (
    "single_first_party",
    "multi_first_party",
    "research_supported",
    "independently_corrob",
    "independently_replicated",
)


def _normalized_evidence_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _is_verbatim(evidence_text: str, item) -> bool:
    needle = _normalized_evidence_text(evidence_text)
    if not needle:
        return False
    return any(
        needle in _normalized_evidence_text(candidate)
        for candidate in (item.content, item.snippet)
        if candidate
    )


def _as_paraphrase(value: str) -> str:
    text = value.strip()
    pairs = (("\u201c", "\u201d"), ('"', '"'), ("\u2018", "\u2019"), ("'", "'"))
    for opening, closing in pairs:
        if text.startswith(opening) and text.endswith(closing) and len(text) > 1:
            return text[1:-1].strip()
    return text


def verification_level_for_pack(pack: EvidencePack) -> str:
    types = [item.source_type for item in pack.items]
    combined = " ".join(
        f"{item.title} {item.snippet} {item.content}" for item in pack.items
    ).casefold()
    has_research = "research" in types
    has_independent = "independent_media" in types
    replication_signals = (
        "independent replication",
        "independently replicated",
        "reproduced the benchmark",
        "reproduced results",
    )
    if has_research and has_independent and any(term in combined for term in replication_signals):
        return "independently_replicated"
    if has_independent:
        return "independently_corrob"
    if has_research:
        return "research_supported"
    official_count = sum(item.source_type == "official" for item in pack.items)
    return "multi_first_party" if official_count >= 2 else "single_first_party"


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
    text = value.strip()
    if not text:
        raise ResearchValidationError("Research response does not contain JSON")
    try:
        result = json.loads(text)
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
    direct_signals = {
        "creator_tools": ("creator tool", "creative tool", "editing tool"),
        "content_creation": (
            "content creation", "audiobook", "narration", "dubbing", "localization pipeline",
        ),
        "short_video": ("short video", "tiktok", "reels", "shorts"),
        "distribution": ("content distribution", "recommendation feed", "creator reach"),
        "community": ("creator community", "user-generated content", "ugc"),
        "moderation": ("content moderation", "trust and safety"),
    }
    indirect_signals = {
        "content_creation": (
            "content drafting", "report drafting", "document workflow", "document parsing",
            "marketing campaign", "image generation", "video generation", "music generation",
        ),
    }
    direct_areas = [
        area for area, terms in direct_signals.items() if any(term in text for term in terms)
    ]
    indirect_areas = [
        area for area, terms in indirect_signals.items() if any(term in text for term in terms)
    ]
    if direct_areas:
        return UGCRelevance(
            level="high" if len(direct_areas) >= 3 else "medium",
            directness="direct",
            reason="The supplied evidence explicitly mentions creator or UGC production workflows.",
            affected_areas=direct_areas,
        )
    if indirect_areas:
        return UGCRelevance(
            level="medium",
            directness="indirect",
            reason="The supplied evidence supports a general content workflow impact, not a creator-specific one.",
            affected_areas=indirect_areas,
        )
    return UGCRelevance(
        level="low",
        directness="none",
        reason=(
            "The supplied evidence does not establish a creator or UGC relationship."
        ),
        affected_areas=[],
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
                    evidence_text=statement,
                    evidence_type=(
                        "verbatim_quote" if _is_verbatim(statement, item) else "paraphrase"
                    ),
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
            claim_confidence=round(confidence, 2),
            verification_level=verification_level_for_pack(pack),
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
        brief = self._validate(_json_object(response), event, pack)
        brief.model_name = str(
            getattr(self.provider, "last_model", None)
            or getattr(self.provider, "model", "")
        ) or None
        raw_usage = getattr(self.provider, "last_usage", {})
        brief.usage = dict(raw_usage) if isinstance(raw_usage, dict) else {}
        return brief

    def _validate(self, data: dict, event: Event, pack: EvidencePack) -> ResearchBrief:
        required_fields = {
            "headline", "executive_summary", "what_happened", "key_facts",
            "background", "why_it_matters", "industry_impact", "ugc_relevance",
            "evidence", "sources", "uncertainties", "claim_confidence",
            "verification_level", "tags",
        }
        missing = required_fields - set(data)
        extra = set(data) - required_fields
        if missing or extra:
            raise ResearchValidationError(
                f"Research JSON schema mismatch; missing={sorted(missing)}, extra={sorted(extra)}"
            )
        allowed = {item.source_id: item for item in pack.items}

        def required_text(key: str) -> str:
            value = data.get(key)
            if not isinstance(value, str) or not value.strip():
                raise ResearchValidationError(f"Missing non-empty field: {key}")
            return value.strip()

        raw_sources = data.get("sources")
        if not isinstance(raw_sources, list) or not raw_sources:
            raise ResearchValidationError("Research sources must be a non-empty list")
        sources = []
        listed_source_ids: set[str] = set()
        for raw in raw_sources:
            if not isinstance(raw, dict):
                raise ResearchValidationError("Research sources must be objects")
            sid = str(raw.get("source_id", ""))
            item = allowed.get(sid)
            if item is None or raw.get("url") != item.url:
                raise ResearchValidationError("Research response contains an unknown source URL or ID")
            if set(raw) != {"source_id", "url"}:
                raise ResearchValidationError("Research sources must match the requested schema")
            if sid in listed_source_ids:
                raise ResearchValidationError("Research sources must not contain duplicate source IDs")
            listed_source_ids.add(sid)
            sources.append(
                ResearchSource(
                    source_id=sid, article_id=item.article_id, title=item.title,
                    source=item.source, url=item.url, source_type=item.source_type,
                )
            )

        raw_evidence = data.get("evidence")
        if not isinstance(raw_evidence, list) or not raw_evidence:
            raise ResearchValidationError("evidence must be a non-empty list")
        evidence = []
        evidence_source_ids: set[str] = set()
        for raw in raw_evidence:
            expected_evidence_fields = {
                "claim", "source_id", "url", "evidence_text", "evidence_type"
            }
            if not isinstance(raw, dict) or set(raw) != expected_evidence_fields:
                raise ResearchValidationError("Evidence entries must match the requested schema")
            sid = str(raw.get("source_id", ""))
            item = allowed.get(sid)
            if item is None or raw.get("url") != item.url:
                raise ResearchValidationError("Evidence refers to an unknown source")
            claim = str(raw.get("claim", "")).strip()
            evidence_text = str(raw.get("evidence_text", "")).strip()
            evidence_type = str(raw.get("evidence_type", "")).strip()
            if not claim or not evidence_text:
                raise ResearchValidationError("Evidence claim and evidence_text must be non-empty")
            if evidence_type not in EVIDENCE_TYPES:
                raise ResearchValidationError("Invalid evidence_type")
            if evidence_type == "verbatim_quote" and not _is_verbatim(evidence_text, item):
                evidence_type = "paraphrase"
                evidence_text = _as_paraphrase(evidence_text)
            if sid not in listed_source_ids:
                raise ResearchValidationError("Evidence source must also appear in sources")
            evidence_source_ids.add(sid)
            evidence.append(
                EvidenceReference(
                    claim=claim, source_id=sid,
                    article_id=item.article_id, url=item.url,
                    evidence_text=evidence_text,
                    evidence_type=evidence_type,
                )
            )

        key_facts = data.get("key_facts")
        if not isinstance(key_facts, list) or not key_facts:
            raise ResearchValidationError("key_facts must be a non-empty list")
        for fact in key_facts:
            if not isinstance(fact, dict) or set(fact) != {"statement", "type", "source_ids"}:
                raise ResearchValidationError("Each key fact must match the requested schema")
            if fact.get("type") not in {"reported_fact", "inference"}:
                raise ResearchValidationError("Each key fact must distinguish reported_fact or inference")
            if not isinstance(fact.get("statement"), str) or not fact["statement"].strip():
                raise ResearchValidationError("Each key fact statement must be non-empty")
            fact_source_ids = fact.get("source_ids")
            if not isinstance(fact_source_ids, list) or not fact_source_ids:
                raise ResearchValidationError("Each key fact must cite at least one source ID")
            if any(str(sid) not in evidence_source_ids for sid in fact_source_ids):
                raise ResearchValidationError("A key fact must cite a validated evidence source")

        raw_ugc = data.get("ugc_relevance")
        if not isinstance(raw_ugc, dict) or set(raw_ugc) != {
            "level", "directness", "reason", "affected_areas"
        }:
            raise ResearchValidationError("ugc_relevance must be a structured object")
        level = str(raw_ugc.get("level", ""))
        directness = str(raw_ugc.get("directness", ""))
        raw_areas = raw_ugc.get("affected_areas")
        if not isinstance(raw_areas, list) or any(not isinstance(item, str) for item in raw_areas):
            raise ResearchValidationError("affected_areas must be a list of strings")
        areas = [item for item in raw_areas]
        if (
            level not in {"low", "medium", "high"}
            or directness not in {"none", "indirect", "direct"}
            or any(area not in UGC_AREAS for area in areas)
        ):
            raise ResearchValidationError("Invalid UGC relevance level, directness, or affected area")
        if directness == "none" and areas:
            raise ResearchValidationError("UGC directness none cannot list affected areas")
        reason = str(raw_ugc.get("reason", "")).strip()
        if not reason:
            raise ResearchValidationError("UGC relevance reason is required")
        raw_confidence = data.get("claim_confidence")
        if isinstance(raw_confidence, bool) or not isinstance(raw_confidence, (int, float)):
            raise ResearchValidationError("claim_confidence must be numeric")
        claim_confidence = float(raw_confidence)
        if not 0 <= claim_confidence <= 1:
            raise ResearchValidationError("claim_confidence must be between 0 and 1")
        raw_verification_level = str(data.get("verification_level", ""))
        if raw_verification_level not in VERIFICATION_LEVELS:
            raise ResearchValidationError("Invalid verification_level")
        verification_level = verification_level_for_pack(pack)
        uncertainties = data.get("uncertainties")
        if not isinstance(uncertainties, list) or any(
            not isinstance(item, str) or not item.strip() for item in uncertainties
        ):
            raise ResearchValidationError("uncertainties must be a list of non-empty strings")
        if pack.coverage_status == "insufficient" and not uncertainties:
            raise ResearchValidationError("Insufficient source coverage requires an uncertainty")
        tags = data.get("tags")
        has_independent_media = any(
            item.source_type == "independent_media" for item in pack.items
        )
        if pack.mode.startswith("multi_source_llm") and not has_independent_media:
            marker = "independent_source_coverage = insufficient"
            if not any(marker in item.casefold() for item in uncertainties):
                raise ResearchValidationError(
                    "Multi-source output without independent media must include the coverage marker"
                )
        if not isinstance(tags, list) or any(not isinstance(item, str) for item in tags):
            raise ResearchValidationError("tags must be a list of strings")

        return ResearchBrief(
            event_id=event.id, headline=required_text("headline"),
            executive_summary=required_text("executive_summary"),
            what_happened=required_text("what_happened"), key_facts=key_facts,
            background=required_text("background"), why_it_matters=required_text("why_it_matters"),
            industry_impact=required_text("industry_impact"),
            ugc_relevance=UGCRelevance(
                level=level, directness=directness, reason=reason, affected_areas=areas
            ),
            evidence=evidence, sources=sources,
            uncertainties=[item.strip() for item in uncertainties],
            claim_confidence=claim_confidence,
            verification_level=verification_level,
            tags=[item.strip() for item in tags if item.strip()][:15],
            provider_name=self.provider_name, research_mode=pack.mode,
            generation_type=self.generation_type, evidence_pack_id=pack.id,
        )
