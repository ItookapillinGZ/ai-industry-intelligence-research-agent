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


@dataclass(slots=True)
class EventGroupingStats:
    articles_considered: int = 0
    events_created: int = 0
    articles_linked: int = 0


@dataclass(slots=True)
class ResearchSource:
    article_id: int
    title: str
    source: str
    url: str


@dataclass(slots=True)
class EvidenceReference:
    claim: str
    article_id: int
    url: str
    excerpt: str


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
    ugc_relevance: str
    evidence: list[EvidenceReference]
    sources: list[ResearchSource]
    uncertainties: list[str]
    confidence: float
    tags: list[str]
    provider_name: str
    id: int | None = None
    created_at: str | None = None
    updated_at: str | None = None


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

