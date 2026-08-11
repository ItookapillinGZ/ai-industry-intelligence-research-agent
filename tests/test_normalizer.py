from __future__ import annotations

import pytest

from app.models import ArticleInput
from app.services.normalizer import normalize_article, normalize_title, normalize_url


def test_normalize_url_removes_tracking_fragment_and_trailing_slash() -> None:
    value = normalize_url(
        "HTTPS://Example.COM:443/path/?utm_source=newsletter&b=2&a=1#section"
    )
    assert value == "https://example.com/path?a=1&b=2"


def test_normalize_title_handles_case_punctuation_and_width() -> None:
    assert normalize_title("  GPT－５: A New Model! ") == "gpt 5 a new model"


def test_normalize_article_rejects_invalid_url() -> None:
    with pytest.raises(ValueError):
        normalize_article(ArticleInput(title="Valid title", url="not-a-url", source="test"))

