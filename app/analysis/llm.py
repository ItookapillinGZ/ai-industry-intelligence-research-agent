from __future__ import annotations

import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.analysis.interfaces import LLMProvider
from app.analysis.taxonomy import CATEGORIES
from app.models import ClassificationResult, StoredArticle


class LLMProviderError(RuntimeError):
    """Raised when an LLM provider request or response fails."""


def _http_error_detail(exc: HTTPError) -> str:
    try:
        payload = json.loads(exc.read().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return ""
    error = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error, dict):
        return ""
    fields = []
    for key in ("message", "type", "param", "code"):
        value = error.get(key)
        if value is not None:
            fields.append(f"{key}={value}")
    detail = "; ".join(fields)[:1000]
    return re.sub(r"sk-[A-Za-z0-9_-]+", "[redacted]", detail)


class OpenAICompatibleProvider:
    """Minimal Chat Completions client; replaceable through the LLMProvider protocol."""

    name = "openai-compatible"

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str,
        timeout_seconds: int = 30,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.last_model: str | None = None
        self.last_usage: dict[str, int | float] = {}

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        body = json.dumps(
            {
                "model": self.model,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            }
        ).encode("utf-8")
        request = Request(
            f"{self.base_url}/chat/completions",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "AI-Industry-Intelligence-Research-Agent/0.2",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
            content = payload["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise KeyError("choices[0].message.content")
            self.last_model = str(payload.get("model") or self.model)
            raw_usage = payload.get("usage")
            self.last_usage = (
                {
                    str(key): value
                    for key, value in raw_usage.items()
                    if isinstance(value, (int, float)) and not isinstance(value, bool)
                }
                if isinstance(raw_usage, dict)
                else {}
            )
            return content.strip()
        except HTTPError as exc:
            detail = _http_error_detail(exc)
            suffix = f": {detail}" if detail else ""
            raise LLMProviderError(f"LLM request failed: HTTP {exc.code}{suffix}") from exc
        except (URLError, TimeoutError, KeyError, IndexError, json.JSONDecodeError) as exc:
            raise LLMProviderError(f"LLM request failed: {exc}") from exc


def _article_prompt(article: StoredArticle) -> str:
    content = (article.content or article.raw_text)[:12000]
    return f"Title: {article.title}\nSource: {article.source}\nContent:\n{content}"


def _parse_json_object(value: str) -> dict:
    match = re.search(r"\{.*\}", value, flags=re.DOTALL)
    if not match:
        raise LLMProviderError("LLM did not return a JSON object")
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise LLMProviderError(f"LLM returned invalid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise LLMProviderError("LLM JSON response must be an object")
    return parsed


class LLMClassifier:

    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider

    def classify(self, article: StoredArticle) -> ClassificationResult:
        response = self.provider.generate(
            "Classify AI industry articles. Return strict JSON only.",
            _article_prompt(article)
            + f"\nChoose one category from {CATEGORIES}. "
            'Return {"category":"...","tags":["..."]}.',
        )
        data = _parse_json_object(response)
        category = str(data.get("category", "Other"))
        if category not in CATEGORIES:
            category = "Other"
        tags = [str(tag) for tag in data.get("tags", []) if str(tag).strip()][:8]
        return ClassificationResult(category=category, tags=tags)


class LLMImportanceScorer:
    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider

    def score(self, article: StoredArticle, classification: ClassificationResult) -> float:
        response = self.provider.generate(
            "Score AI industry news importance from 0 to 10. Return only a number.",
            _article_prompt(article) + f"\nCategory: {classification.category}",
        )
        match = re.search(r"(?:10(?:\.0+)?|[0-9](?:\.\d+)?)", response)
        if not match:
            raise LLMProviderError("LLM did not return a numeric score")
        return max(0.0, min(10.0, float(match.group(0))))


class LLMSummarizer:
    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider

    def summarize(self, article: StoredArticle) -> str:
        return self.provider.generate(
            "Write a factual 2-3 sentence research brief. Do not invent details.",
            _article_prompt(article),
        ).strip()

