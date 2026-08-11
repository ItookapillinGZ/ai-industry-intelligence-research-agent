from __future__ import annotations

from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import trafilatura

from app.content.interfaces import ContentExtractionError, ExtractedContent


class TrafilaturaContentExtractor:
    def __init__(
        self,
        timeout_seconds: int = 20,
        min_length: int = 200,
        max_bytes: int = 5_000_000,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.min_length = min_length
        self.max_bytes = max_bytes

    def extract(self, url: str) -> ExtractedContent:
        request = Request(
            url,
            headers={
                "User-Agent": "AI-Industry-Intelligence-Research-Agent/0.2 (+research workflow)",
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                content_type = response.headers.get_content_type()
                if content_type not in {"text/html", "application/xhtml+xml"}:
                    raise ContentExtractionError(
                        "unsupported-content-type", f"Unsupported content type: {content_type}"
                    )
                payload = response.read(self.max_bytes + 1)
                if len(payload) > self.max_bytes:
                    raise ContentExtractionError(
                        "response-too-large", f"Response exceeds {self.max_bytes} bytes"
                    )
                charset = response.headers.get_content_charset() or "utf-8"
        except HTTPError as exc:
            raise ContentExtractionError(f"http-{exc.code}", f"HTTP {exc.code} for {url}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise ContentExtractionError("fetch-failed", f"Could not fetch {url}: {exc}") from exc

        html = payload.decode(charset, errors="replace")
        try:
            text = trafilatura.extract(
                html,
                url=url,
                output_format="txt",
                include_comments=False,
                include_tables=False,
                favor_precision=True,
            )
        except Exception as exc:
            raise ContentExtractionError("parse-failed", f"Extraction failed: {exc}") from exc

        cleaned = "\n".join(line.strip() for line in (text or "").splitlines() if line.strip())
        if len(cleaned) < self.min_length:
            raise ContentExtractionError(
                "insufficient-content",
                f"Extracted content is shorter than {self.min_length} characters",
            )
        return ExtractedContent(text=cleaned)

