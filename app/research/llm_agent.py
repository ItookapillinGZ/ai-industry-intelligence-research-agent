from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path

from app.analysis.interfaces import LLMProvider
from app.models import EvidenceReference, Event, ResearchBrief, ResearchSource, StoredArticle


class ResearchValidationError(ValueError):
    """Raised when a model response is invalid or cites supplied-external evidence."""


class PromptLoader:
    def __init__(self, prompts_dir: Path) -> None:
        self.prompts_dir = prompts_dir

    def load(self, name: str) -> str:
        path = self.prompts_dir / name
        if not path.exists():
            raise FileNotFoundError(f"Research prompt not found: {path}")
        return path.read_text(encoding="utf-8")


def _json_object(value: str) -> dict:
    match = re.search(r"\{.*\}", value, flags=re.DOTALL)
    if not match:
        raise ResearchValidationError("Research response does not contain JSON")
    try:
        result = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise ResearchValidationError(f"Invalid research JSON: {exc}") from exc
    if not isinstance(result, dict):
        raise ResearchValidationError("Research JSON must be an object")
    return result


class LLMResearchAgent:
    def __init__(self, provider: LLMProvider, prompts_dir: Path) -> None:
        self.provider = provider
        self.provider_name = provider.name
        self.prompts = PromptLoader(prompts_dir)

    def research(self, event: Event, articles: list[StoredArticle]) -> ResearchBrief:
        supplied = [
            {
                "article_id": article.id,
                "title": article.title,
                "source": article.source,
                "url": article.url,
                "published_at": article.published_at,
                "summary": article.summary,
                "content": (article.content or article.raw_text)[:12000],
            }
            for article in articles
        ]
        template = self.prompts.load("research_event.txt")
        user_prompt = template.replace(
            "{{EVENT_JSON}}", json.dumps(asdict(event), ensure_ascii=False)
        ).replace("{{ARTICLES_JSON}}", json.dumps(supplied, ensure_ascii=False))
        response = self.provider.generate(self.prompts.load("research_system.txt"), user_prompt)
        return self._validate(_json_object(response), event, articles)

    def _validate(
        self,
        data: dict,
        event: Event,
        articles: list[StoredArticle],
    ) -> ResearchBrief:
        allowed_urls = {article.url: article for article in articles}
        allowed_ids = {article.id for article in articles}

        def required_text(key: str) -> str:
            value = data.get(key)
            if not isinstance(value, str) or not value.strip():
                raise ResearchValidationError(f"Missing non-empty field: {key}")
            return value.strip()

        raw_sources = data.get("sources")
        if not isinstance(raw_sources, list) or not raw_sources:
            raise ResearchValidationError("Research sources must be a non-empty list")
        sources: list[ResearchSource] = []
        for item in raw_sources:
            if not isinstance(item, dict) or item.get("url") not in allowed_urls:
                raise ResearchValidationError("Research response contains an unknown source URL")
            article = allowed_urls[item["url"]]
            sources.append(
                ResearchSource(
                    article_id=article.id,
                    title=article.title,
                    source=article.source,
                    url=article.url,
                )
            )

        raw_evidence = data.get("evidence", [])
        if not isinstance(raw_evidence, list):
            raise ResearchValidationError("Evidence must be a list")
        evidence: list[EvidenceReference] = []
        for item in raw_evidence:
            if not isinstance(item, dict):
                raise ResearchValidationError("Evidence entries must be objects")
            article_id = int(item.get("article_id", -1))
            url = str(item.get("url", ""))
            if article_id not in allowed_ids or url not in allowed_urls:
                raise ResearchValidationError("Evidence refers to an unknown article")
            evidence.append(
                EvidenceReference(
                    claim=str(item.get("claim", "")).strip(),
                    article_id=article_id,
                    url=url,
                    excerpt=str(item.get("excerpt", "")).strip(),
                )
            )

        key_facts = data.get("key_facts")
        if not isinstance(key_facts, list):
            raise ResearchValidationError("key_facts must be a list")
        for fact in key_facts:
            if not isinstance(fact, dict) or fact.get("type") not in {"reported_fact", "inference"}:
                raise ResearchValidationError("Each key fact must distinguish reported_fact or inference")
            referenced = fact.get("source_article_ids", [])
            if any(int(article_id) not in allowed_ids for article_id in referenced):
                raise ResearchValidationError("A key fact refers to an unknown article")

        confidence = float(data.get("confidence", -1))
        if not 0 <= confidence <= 1:
            raise ResearchValidationError("confidence must be between 0 and 1")
        uncertainties = data.get("uncertainties", [])
        tags = data.get("tags", [])
        if not isinstance(uncertainties, list) or not isinstance(tags, list):
            raise ResearchValidationError("uncertainties and tags must be lists")

        return ResearchBrief(
            event_id=event.id,
            headline=required_text("headline"),
            executive_summary=required_text("executive_summary"),
            what_happened=required_text("what_happened"),
            key_facts=key_facts,
            background=required_text("background"),
            why_it_matters=required_text("why_it_matters"),
            industry_impact=required_text("industry_impact"),
            ugc_relevance=required_text("ugc_relevance"),
            evidence=evidence,
            sources=sources,
            uncertainties=[str(item) for item in uncertainties],
            confidence=confidence,
            tags=[str(item) for item in tags][:15],
            provider_name=self.provider_name,
        )


# Phase 2.5 validates source IDs and URLs against an Evidence Pack.
from app.research.evidence_analyst import (
    EvidenceBoundLLMAnalyst as LLMResearchAgent,
)
from app.research.evidence_analyst import (
    ResearchValidationError as ResearchValidationError,
)
