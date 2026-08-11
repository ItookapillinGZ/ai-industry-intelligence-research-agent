from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ExtractedContent:
    text: str


class ContentExtractionError(RuntimeError):
    def __init__(self, status: str, message: str) -> None:
        super().__init__(message)
        self.status = status


class ContentExtractor(Protocol):
    def extract(self, url: str) -> ExtractedContent: ...

