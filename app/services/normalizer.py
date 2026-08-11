from __future__ import annotations

import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.models import ArticleInput, NormalizedArticle

TRACKING_PARAMETERS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "ref_src",
}


def normalize_url(url: str) -> str:
    value = url.strip()
    parts = urlsplit(value)
    scheme = parts.scheme.lower() or "https"
    hostname = (parts.hostname or "").lower()
    if not hostname:
        raise ValueError(f"Invalid URL: {url}")

    port = parts.port
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{hostname}:{port}"
    else:
        netloc = hostname

    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if path != "/":
        path = path.rstrip("/")

    query_items = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in TRACKING_PARAMETERS
    ]
    query = urlencode(sorted(query_items))
    return urlunsplit((scheme, netloc, path, query, ""))


def normalize_title(title: str) -> str:
    value = unicodedata.normalize("NFKC", title).casefold()
    value = "".join(character if character.isalnum() else " " for character in value)
    return " ".join(value.split())


def normalize_article(article: ArticleInput) -> NormalizedArticle:
    if not article.title.strip():
        raise ValueError("Article title cannot be empty")
    return NormalizedArticle(
        article=article,
        normalized_url=normalize_url(article.url),
        normalized_title=normalize_title(article.title),
    )

