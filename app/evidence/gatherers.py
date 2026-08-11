from __future__ import annotations

import hashlib
import logging
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import feedparser

from app.evidence.interfaces import EvidenceSearchClient, SearchResult
from app.evidence.queries import build_evidence_queries
from app.evidence.source_types import (
    canonical_search_url,
    classify_source_type,
    hostname,
)
from app.models import EvidenceItem, EvidencePack, Event, StoredArticle
from app.services.normalizer import normalize_url

logger = logging.getLogger(__name__)


def source_id(url: str) -> str:
    digest = hashlib.sha256(normalize_url(url).encode("utf-8")).hexdigest()[:16]
    return f"src_{digest}"


def _clean_html(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value or "")).strip()

MATCH_STOP_WORDS = {
    "about", "agent", "agents", "artificial", "build", "coming", "from",
    "introducing", "launch", "launches", "making", "model", "models", "open",
    "release", "released", "source", "using", "with",
}


def _title_tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", value.casefold())
        if len(token) >= 3 and token not in MATCH_STOP_WORDS
    }


def _is_relevant_candidate(event_title: str, candidate_title: str) -> bool:
    shared = _title_tokens(event_title) & _title_tokens(candidate_title)
    return len(shared) >= 2 or any(len(token) >= 8 for token in shared)




def _coverage(items: list[EvidenceItem]) -> tuple[str, str]:
    official = len({item.url for item in items if item.source_type == "official"})
    independent = len({item.url for item in items if item.source_type == "independent"})
    status = "sufficient" if official >= 1 and independent >= 1 else "insufficient"
    note = (
        f"official={official}, independent={independent}; "
        "target is at least 1 official and 1-2 independent sources."
    )
    return status, note


def _seed_items(event: Event, articles: list[StoredArticle]) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []
    seen: set[str] = set()
    for article in sorted(
        articles,
        key=lambda item: (item.importance_score or 0, item.published_at or item.collected_at),
        reverse=True,
    ):
        try:
            url = normalize_url(article.url)
        except ValueError:
            continue
        if url in seen:
            continue
        seen.add(url)
        items.append(
            EvidenceItem(
                source_id=source_id(url),
                article_id=article.id,
                title=article.title,
                source=article.source,
                url=url,
                source_type=classify_source_type(url, article.source, event.title),
                published_at=article.published_at,
                snippet=article.summary or article.raw_text,
                content=article.content or "",
                is_seed=True,
            )
        )
    return items


class SeedEvidenceGatherer:
    def __init__(self, mode: str, max_sources: int | None = None) -> None:
        self.mode = mode
        self.max_sources = max_sources

    def gather(self, event: Event, seed_articles: list[StoredArticle]) -> EvidencePack:
        items = _seed_items(event, seed_articles)
        if self.max_sources is not None:
            items = items[: self.max_sources]
        status, note = _coverage(items)
        return EvidencePack(
            event_id=event.id,
            mode=self.mode,
            queries=[],
            items=items,
            coverage_status=status,
            coverage_note=note,
        )


class BingNewsSearchClient:
    """Small RSS search adapter. It returns URLs supplied by search, never model-generated URLs."""

    def __init__(self, timeout_seconds: int = 20, market: str = "en-US") -> None:
        self.timeout_seconds = timeout_seconds
        self.market = market

    def search(self, query: str, limit: int) -> list[SearchResult]:
        params = urlencode({"q": query, "format": "rss", "mkt": self.market})
        request = Request(
            f"https://www.bing.com/news/search?{params}",
            headers={"User-Agent": "AI-Industry-Intelligence-Research-Agent/0.3"},
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            parsed = feedparser.parse(response.read())
        results: list[SearchResult] = []
        for entry in parsed.entries[:limit]:
            source = entry.get("source", {})
            if isinstance(source, dict):
                source_name = str(source.get("title", "")).strip()
            else:
                source_name = str(source).strip()
            results.append(
                SearchResult(
                    title=str(entry.get("title", "")).strip(),
                    source=source_name or "Unknown source",
                    url=str(entry.get("link", "")).strip(),
                    published_at=str(entry.get("published", "")).strip() or None,
                    snippet=_clean_html(str(entry.get("summary", ""))),
                )
            )
        return [item for item in results if item.title and item.url]


class SearchEvidenceGatherer:
    mode = "multi_source_llm"

    def __init__(
        self,
        search_client: EvidenceSearchClient,
        results_per_query: int = 5,
        max_candidates: int = 8,
    ) -> None:
        self.search_client = search_client
        self.results_per_query = results_per_query
        self.max_candidates = max_candidates

    def gather(self, event: Event, seed_articles: list[StoredArticle]) -> EvidencePack:
        items = _seed_items(event, seed_articles)
        queries = build_evidence_queries(event, seed_articles)
        seen = {item.url for item in items}
        official_domains = {
            hostname(item.url) for item in items if item.source_type == "official"
        }
        errors: list[str] = []

        for query in queries:
            try:
                results = self.search_client.search(query, self.results_per_query)
            except Exception as exc:
                errors.append(f"{query}: {type(exc).__name__}: {exc}")
                logger.warning("Evidence search failed for event %s query %r: %s", event.id, query, exc)
                continue
            for result in results:
                try:
                    url = canonical_search_url(result.url)
                except ValueError:
                    continue
                if url in seen:
                    continue
                if not _is_relevant_candidate(event.title, result.title):
                    continue
                seen.add(url)
                items.append(
                    EvidenceItem(
                        source_id=source_id(url),
                        title=result.title,
                        source=result.source if result.source != "Unknown source" else hostname(url),
                        url=url,
                        source_type=classify_source_type(
                            url,
                            result.source,
                            event.title,
                            official_domains,
                        ),
                        published_at=result.published_at,
                        snippet=result.snippet,
                    )
                )

        seeds = [item for item in items if item.is_seed]
        candidates = [item for item in items if not item.is_seed]
        ranked = sorted(
            candidates,
            key=lambda item: (
                {"official": 0, "independent": 1, "research": 2, "community": 3, "other": 4}[
                    item.source_type
                ],
                item.source,
                item.title,
            ),
        )
        caps = {"official": 1, "independent": 2, "research": 1, "community": 1, "other": 1}
        counts = {
            source_type: sum(item.source_type == source_type for item in seeds)
            for source_type in caps
        }
        preferred = []
        for item in ranked:
            if counts[item.source_type] >= caps[item.source_type]:
                continue
            preferred.append(item)
            counts[item.source_type] += 1
            if len(preferred) >= self.max_candidates:
                break
        selected = [*seeds, *preferred]
        status, note = _coverage(selected)
        if errors:
            note += f" Search errors={len(errors)}."
        return EvidencePack(
            event_id=event.id,
            mode=self.mode,
            queries=queries,
            items=selected,
            coverage_status=status,
            coverage_note=note,
            errors=errors,
        )
