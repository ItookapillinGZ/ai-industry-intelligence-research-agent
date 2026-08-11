from __future__ import annotations

from typing import Protocol

from app.models import Event, ResearchBrief, StoredArticle


class ResearchAgent(Protocol):
    provider_name: str

    def research(self, event: Event, articles: list[StoredArticle]) -> ResearchBrief: ...

