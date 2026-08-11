from __future__ import annotations

import re
from urllib.parse import parse_qs, unquote, urlsplit

from app.services.normalizer import normalize_url

SOURCE_TYPES = ("official", "independent", "community", "research", "other")

COMMUNITY_DOMAINS = {
    "discord.com",
    "github.com",
    "news.ycombinator.com",
    "reddit.com",
    "x.com",
    "youtube.com",
}
RESEARCH_DOMAINS = {
    "aclanthology.org",
    "arxiv.org",
    "nature.com",
    "openreview.net",
    "pubmed.ncbi.nlm.nih.gov",
    "science.org",
}
AI_ORGANIZATION_DOMAINS = {
    "anthropic.com",
    "cohere.com",
    "deepmind.google",
    "github.com",
    "googleblog.com",
    "huggingface.co",
    "meta.com",
    "microsoft.com",
    "mistral.ai",
    "nvidia.com",
    "openai.com",
    "stability.ai",
}


def hostname(url: str) -> str:
    return (urlsplit(url).hostname or "").casefold().removeprefix("www.")


def _matches(domain: str, candidates: set[str]) -> bool:
    return any(domain == item or domain.endswith("." + item) for item in candidates)


def classify_source_type(
    url: str,
    source_name: str,
    event_title: str = "",
    official_domains: set[str] | None = None,
) -> str:
    domain = hostname(url)
    source_text = source_name.casefold()
    if _matches(domain, COMMUNITY_DOMAINS):
        return "community"
    if _matches(domain, RESEARCH_DOMAINS) or any(
        term in source_text for term in ("journal", "university", "research paper", "arxiv")
    ):
        return "research"
    if domain.endswith(".gov") or _matches(domain, official_domains or set()):
        return "official"
    if _matches(domain, AI_ORGANIZATION_DOMAINS):
        return "official"

    title_tokens = {
        token for token in re.findall(r"[a-z0-9]+", event_title.casefold()) if len(token) >= 4
    }
    domain_tokens = set(re.findall(r"[a-z0-9]+", domain))
    if title_tokens & domain_tokens:
        return "official"
    return "independent" if domain else "other"


def canonical_search_url(url: str) -> str:
    parts = urlsplit(url)
    if hostname(url).endswith("bing.com"):
        query = parse_qs(parts.query)
        for key in ("url", "u", "target"):
            value = query.get(key)
            if value:
                candidate = unquote(value[0])
                if candidate.startswith(("http://", "https://")):
                    return normalize_url(candidate)
    return normalize_url(url)
