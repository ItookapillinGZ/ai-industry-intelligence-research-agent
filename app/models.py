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

