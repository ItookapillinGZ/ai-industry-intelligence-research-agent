from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(slots=True)
class ArticleInput:
    title: str
    url: str
    source: str
    author: str | None = None
    published_at: str | None = None
    collected_at: str = field(default_factory=utc_now_iso)
    raw_text: str = ""
    tags: list[str] = field(default_factory=list)


@dataclass(slots=True)
class NormalizedArticle:
    article: ArticleInput
    normalized_url: str
    normalized_title: str


@dataclass(slots=True)
class StoredArticle:
    id: int
    title: str
    url: str
    source: str
    author: str | None
    published_at: str | None
    collected_at: str
    raw_text: str
    summary: str | None
    category: str | None
    importance_score: float | None
    tags: list[str]
    normalized_url: str
    normalized_title: str
    processing_status: str
    llm_provider: str | None
    content: str | None = None
    content_status: str = "pending"
    content_length: int = 0
    content_fetched_at: str | None = None
    content_error: str | None = None


@dataclass(slots=True)
class ClassificationResult:
    category: str
    tags: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CollectionStats:
    fetched: int = 0
    inserted: int = 0
    duplicate_url: int = 0
    duplicate_title: int = 0
    invalid: int = 0
    source_errors: int = 0


@dataclass(slots=True)
class ContentFetchStats:
    attempted: int = 0
    fetched: int = 0
    failed: int = 0
    skipped: int = 0


@dataclass(slots=True)
class Event:
    id: int
    title: str
    normalized_title: str
    category: str
    created_at: str
    updated_at: str
    importance_score: float
    article_count: int
    source_count: int
    importance_factors: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class EventGroupingStats:
    articles_considered: int = 0
    events_created: int = 0
    articles_linked: int = 0




@dataclass(slots=True)
class EvidenceItem:
    source_id: str
    title: str
    source: str
    url: str
    source_type: str
    article_id: int | None = None
    published_at: str | None = None
    snippet: str = ""
    content: str = ""
    is_seed: bool = False


@dataclass(slots=True)
class EvidencePack:
    event_id: int
    mode: str
    queries: list[str]
    items: list[EvidenceItem]
    coverage_status: str
    coverage_note: str
    errors: list[str] = field(default_factory=list)
    id: int | None = None
    created_at: str | None = None
    updated_at: str | None = None


@dataclass(slots=True)
class UGCRelevance:
    level: str
    directness: str
    reason: str
    affected_areas: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ImportanceBreakdown:
    novelty: float
    industry_magnitude: float
    source_authority: float
    source_diversity: float
    ecosystem_impact: float
    developer_impact: float
    creator_impact: float
    recency: float
    total: float

@dataclass(slots=True)
class ResearchSource:
    article_id: int | None
    title: str
    source: str
    url: str


    source_id: str = ""
    source_type: str = "other"
@dataclass(slots=True)
class EvidenceReference:
    claim: str
    article_id: int | None
    url: str
    evidence_text: str
    evidence_type: str
    source_id: str = ""

    @property
    def excerpt(self) -> str:
        """Deprecated read-only alias for Phase 2/2.6 callers."""
        return self.evidence_text

@dataclass(slots=True)
class ResearchBrief:
    event_id: int
    headline: str
    executive_summary: str
    what_happened: str
    key_facts: list[dict[str, object]]
    background: str
    why_it_matters: str
    industry_impact: str
    ugc_relevance: UGCRelevance
    evidence: list[EvidenceReference]
    sources: list[ResearchSource]
    uncertainties: list[str]
    claim_confidence: float
    verification_level: str
    tags: list[str]
    provider_name: str
    research_mode: str = "deterministic"
    generation_type: str = "deterministic"
    evidence_pack_id: int | None = None
    id: int | None = None
    created_at: str | None = None
    updated_at: str | None = None
    model_name: str | None = None
    usage: dict[str, int | float] = field(default_factory=dict)

    @property
    def confidence(self) -> float:
        """Deprecated compatibility alias for Phase 2/2.6 readers."""
        return self.claim_confidence


@dataclass(slots=True)
class EvaluationResult:
    research_brief_id: int
    evaluator: str
    factuality: int
    source_coverage: int
    relevance: int
    insightfulness: int
    clarity: int
    notes: str = ""
    id: int | None = None
    created_at: str | None = None

