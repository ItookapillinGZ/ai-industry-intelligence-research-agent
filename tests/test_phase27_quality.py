from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.analysis.fallback import KeywordClassifier
from app.events.importance import AuditableEventScorer
from app.models import (
    EvidenceItem,
    EvidencePack,
    EvidenceReference,
    Event,
    ResearchBrief,
    StoredArticle,
    UGCRelevance,
)
from app.research.evidence_analyst import (
    DeterministicEvidenceAnalyst,
    EvidenceBoundLLMAnalyst,
    verification_level_for_pack,
)
from app.research.reporter import ResearchReportGenerator
from app.storage.research_repository import ResearchRepository


class StaticProvider:
    name = "test-provider"

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        raise AssertionError("The validator test must not make an API call")


def _event(event_id: int = 1, title: str = "Model release", category: str = "Foundation Model") -> Event:
    now = datetime.now(timezone.utc).isoformat()
    return Event(event_id, title, title.casefold(), category, now, now, 0, 1, 1)


def _article(article_id: int, title: str, content: str, category: str) -> StoredArticle:
    now = datetime.now(timezone.utc).isoformat()
    return StoredArticle(
        id=article_id,
        title=title,
        url=f"https://example.com/{article_id}",
        source="Official source",
        author=None,
        published_at=now,
        collected_at=now,
        raw_text=content,
        summary=content,
        category=category,
        importance_score=5,
        tags=[],
        normalized_url=f"https://example.com/{article_id}",
        normalized_title=title.casefold(),
        processing_status="processed",
        llm_provider="test",
        content=content,
        content_status="fetched",
        content_length=len(content),
    )


def _pack(content: str, source_type: str = "official", mode: str = "single_source_llm") -> EvidencePack:
    return EvidencePack(
        event_id=1,
        mode=mode,
        queries=[],
        items=[
            EvidenceItem(
                source_id="src_1",
                title="Source",
                source="Publisher",
                url="https://example.com/source",
                source_type=source_type,
                snippet="OpenAI released a new model.",
                content=content,
            )
        ],
        coverage_status="insufficient",
        coverage_note="Single source",
    )


def _payload(evidence_text: str, evidence_type: str) -> dict:
    return {
        "headline": "Model release",
        "executive_summary": "OpenAI released a model.",
        "what_happened": "OpenAI released a model.",
        "key_facts": [
            {"statement": "OpenAI released a model.", "type": "reported_fact", "source_ids": ["src_1"]}
        ],
        "background": "No additional background is supplied.",
        "why_it_matters": "It may affect model competition.",
        "industry_impact": "Impact remains uncertain.",
        "ugc_relevance": {
            "level": "low",
            "directness": "none",
            "reason": "No creator relationship is supplied.",
            "affected_areas": [],
        },
        "evidence": [
            {
                "claim": "OpenAI released a model.",
                "source_id": "src_1",
                "url": "https://example.com/source",
                "evidence_text": evidence_text,
                "evidence_type": evidence_type,
            }
        ],
        "sources": [{"source_id": "src_1", "url": "https://example.com/source"}],
        "uncertainties": ["Only one source is supplied."],
        "claim_confidence": 0.7,
        "verification_level": "single_first_party",
        "tags": ["Foundation Model"],
    }


def test_valid_verbatim_quote_is_preserved() -> None:
    pack = _pack("OpenAI released a new model. It is available today.")
    brief = EvidenceBoundLLMAnalyst(StaticProvider(), Path("prompts"))._validate(
        _payload("OpenAI released a new model.", "verbatim_quote"), _event(), pack
    )
    assert brief.evidence[0].evidence_type == "verbatim_quote"
    assert brief.evidence[0].evidence_text == "OpenAI released a new model."


def test_fake_verbatim_quote_is_downgraded_to_paraphrase() -> None:
    pack = _pack("OpenAI released a new model.")
    brief = EvidenceBoundLLMAnalyst(StaticProvider(), Path("prompts"))._validate(
        _payload('"OpenAI dramatically reinvented every model."', "verbatim_quote"),
        _event(),
        pack,
    )
    assert brief.evidence[0].evidence_type == "paraphrase"
    assert brief.evidence[0].evidence_text == "OpenAI dramatically reinvented every model."


def test_paraphrase_is_not_rendered_as_a_quote() -> None:
    brief = ResearchBrief(
        event_id=1,
        headline="Headline",
        executive_summary="Summary",
        what_happened="What happened",
        key_facts=[],
        background="Background",
        why_it_matters="Why",
        industry_impact="Impact",
        ugc_relevance=UGCRelevance("low", "none", "No creator evidence.", []),
        evidence=[
            EvidenceReference(
                claim="Claim",
                article_id=1,
                url="https://example.com/source",
                evidence_text="This is a summary of the source.",
                evidence_type="paraphrase",
                source_id="src_1",
            )
        ],
        sources=[],
        uncertainties=[],
        claim_confidence=0.5,
        verification_level="single_first_party",
        tags=[],
        provider_name="test",
    )
    rendered = "\n".join(ResearchReportGenerator(None, Path("reports"))._render_event(1, 1, "Other", brief))
    assert "Paraphrase: This is a summary of the source." in rendered
    assert "> This is a summary of the source." not in rendered


def test_legacy_evidence_remains_readable(repository) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with repository.database.connect() as connection:
        event_id = int(
            connection.execute(
                """
                INSERT INTO events (
                    title, normalized_title, category, created_at, updated_at,
                    importance_score, article_count, source_count
                ) VALUES ('Legacy', 'legacy', 'Other', ?, ?, 1, 1, 1)
                """,
                (now, now),
            ).lastrowid
        )
    runs = ResearchRepository(repository.database)
    saved = runs.save(
        ResearchBrief(
            event_id=event_id,
            headline="Legacy",
            executive_summary="Summary",
            what_happened="What",
            key_facts=[],
            background="Background",
            why_it_matters="Why",
            industry_impact="Impact",
            ugc_relevance=UGCRelevance("low", "none", "No creator evidence.", []),
            evidence=[],
            sources=[],
            uncertainties=[],
            claim_confidence=0.4,
            verification_level="single_first_party",
            tags=[],
            provider_name="legacy",
        )
    )
    with repository.database.connect() as connection:
        connection.execute(
            "UPDATE research_brief_runs SET evidence = ? WHERE id = ?",
            (json.dumps([{"claim": "Legacy claim", "article_id": 1, "url": "https://example.com", "excerpt": "Legacy text"}]), saved.id),
        )
    loaded = runs.get(saved.id)
    assert loaded.evidence[0].evidence_text == "Legacy text"
    assert loaded.evidence[0].evidence_type == "paraphrase"


def test_verification_level_uses_source_types_not_domain_count() -> None:
    pack = _pack("Claim", source_type="official")
    pack.items.append(
        EvidenceItem("src_2", "Discussion", "Community", "https://other.example/post", "community", content="Discussion")
    )
    assert verification_level_for_pack(pack) == "single_first_party"
    pack.items[1].source_type = "official"
    assert verification_level_for_pack(pack) == "multi_first_party"


def test_category_precedence_handles_products_and_preserves_cybersecurity() -> None:
    atl = _article(1, "Empowering educators with ATL Saathi", "A Gemini-powered AI tool and web application for teachers.", "Other")
    premium = _article(2, "Premium seats are coming to ChatGPT Business", "A workspace pricing and usage limit update.", "Other")
    cyber = _article(3, "Third-party cyber evaluations involving OpenAI models", "Independent cybersecurity evaluation.", "Other")
    classifier = KeywordClassifier()
    assert classifier.classify(atl).category == "AI Product"
    assert classifier.classify(premium).category == "AI Product"
    assert classifier.classify(cyber).category == "Cybersecurity"


def test_major_model_release_outranks_limited_product_pilot() -> None:
    scorer = AuditableEventScorer()
    gemini = _article(1, "Introducing a new Gemini model release", "Available today through the API for developers and agentic workflows.", "Foundation Model")
    atl = _article(2, "AI education tool pilot", "A web application rolling out to an initial cohort of 100 pilot schools.", "AI Product")
    assert scorer.score(_event(1, gemini.title, "Foundation Model"), [gemini]) > scorer.score(
        _event(2, atl.title, "AI Product"), [atl]
    )


def test_ugc_directness_distinguishes_direct_indirect_and_none() -> None:
    analyst = DeterministicEvidenceAnalyst()
    direct = analyst.analyze(_event(), _pack("Creator tools support audiobook narration and dubbing workflows."))
    indirect = analyst.analyze(_event(), _pack("The model supports document parsing and report drafting."))
    none = analyst.analyze(_event(), _pack("The pilot helps teachers create robotics lesson plans."))
    assert (direct.ugc_relevance.level, direct.ugc_relevance.directness) == ("medium", "direct")
    assert (indirect.ugc_relevance.level, indirect.ugc_relevance.directness) == ("medium", "indirect")
    assert (none.ugc_relevance.level, none.ugc_relevance.directness) == ("low", "none")
