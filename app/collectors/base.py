from __future__ import annotations

from typing import Protocol

from app.config import RSSSourceConfig
from app.models import ArticleInput


class Collector(Protocol):
    def collect(self, source: RSSSourceConfig) -> list[ArticleInput]: ...

