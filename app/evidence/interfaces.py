from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.models import EvidencePack, Event, StoredArticle


@dataclass(frozen=True, slots=True)
class SearchResult:
    title: str
    source: str
    url: str
    published_at: str | None = None
    snippet: str = ""


class EvidenceSearchClient(Protocol):
    def search(self, query: str, limit: int) -> list[SearchResult]: ...


class EvidenceGatherer(Protocol):
    mode: str

    def gather(self, event: Event, seed_articles: list[StoredArticle]) -> EvidencePack: ...
