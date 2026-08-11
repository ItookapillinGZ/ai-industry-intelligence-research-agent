from __future__ import annotations

from app.content.interfaces import ContentExtractionError, ExtractedContent
from app.content.service import ContentExtractionService
from app.models import ArticleInput
from app.services.normalizer import normalize_article
from app.storage.article_repository import ArticleRepository


class FakeExtractor:
    def __init__(self, failures: set[str] | None = None) -> None:
        self.failures = failures or set()
        self.calls: list[str] = []

    def extract(self, url: str) -> ExtractedContent:
        self.calls.append(url)
        if url in self.failures:
            raise ContentExtractionError("http-403", "forbidden")
        return ExtractedContent(text="Full article content " * 30)


def _insert(repository: ArticleRepository, title: str, url: str) -> int:
    return repository.insert(normalize_article(ArticleInput(title=title, url=url, source="Test")))


def test_content_extraction_isolates_article_errors(repository: ArticleRepository) -> None:
    good_id = _insert(repository, "Good article", "https://example.com/good")
    bad_id = _insert(repository, "Blocked article", "https://example.com/blocked")
    extractor = FakeExtractor({"https://example.com/blocked"})

    stats = ContentExtractionService(repository, extractor).fetch(limit=10)

    assert (stats.fetched, stats.failed) == (1, 1)
    assert repository.get(good_id).content_status == "fetched"
    assert repository.get(good_id).content_length > 0
    assert repository.get(bad_id).content_status == "failed"
    assert "http-403" in repository.get(bad_id).content_error


def test_successfully_fetched_content_is_not_downloaded_again(
    repository: ArticleRepository,
) -> None:
    article_id = _insert(repository, "Already fetched", "https://example.com/fetched")
    extractor = FakeExtractor()
    service = ContentExtractionService(repository, extractor)
    assert service.fetch(limit=10).fetched == 1
    assert service.fetch(limit=10).attempted == 0
    assert extractor.calls == ["https://example.com/fetched"]
    assert repository.get(article_id).raw_text == ""

