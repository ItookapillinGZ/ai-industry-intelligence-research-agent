from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


class ConfigurationError(ValueError):
    """Raised when application configuration is invalid."""


@dataclass(frozen=True, slots=True)
class RSSSourceConfig:
    name: str
    url: str
    enabled: bool = True
    tags: tuple[str, ...] = ()
    max_items: int = 100


@dataclass(frozen=True, slots=True)
class AppConfig:
    database_path: Path
    reports_dir: Path
    logs_dir: Path
    request_timeout_seconds: int = 20
    title_similarity_threshold: float = 0.92
    dedup_lookback_days: int = 30
    processing_batch_size: int = 50
    report_max_articles: int = 100
    content_timeout_seconds: int = 20
    content_min_length: int = 200
    content_max_bytes: int = 5_000_000
    content_batch_size: int = 20
    event_time_window_days: int = 7
    event_similarity_threshold: float = 0.62
    event_batch_size: int = 500
    research_top_k: int = 10
    prompts_dir: Path = Path("prompts")
    sources: tuple[RSSSourceConfig, ...] = field(default_factory=tuple)


def _required(mapping: dict[str, Any], key: str, context: str) -> Any:
    value = mapping.get(key)
    if value is None or value == "":
        raise ConfigurationError(f"Missing required field '{key}' in {context}")
    return value


def _positive_int(mapping: dict[str, Any], key: str, default: int) -> int:
    value = int(mapping.get(key, default))
    if value < 1:
        raise ConfigurationError(f"{key} must be positive")
    return value


def load_config(path: str | Path | None = None) -> AppConfig:
    load_dotenv()
    config_path = Path(path or os.getenv("AI_INTEL_CONFIG_PATH", "config/sources.yaml"))
    if not config_path.exists():
        raise ConfigurationError(f"Configuration file not found: {config_path}")

    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigurationError(f"Invalid YAML in {config_path}: {exc}") from exc

    app = raw.get("app", {})
    source_items = raw.get("sources", [])
    if not isinstance(source_items, list):
        raise ConfigurationError("'sources' must be a list")

    sources: list[RSSSourceConfig] = []
    for index, item in enumerate(source_items):
        if not isinstance(item, dict):
            raise ConfigurationError(f"Source #{index + 1} must be a mapping")
        max_items = int(item.get("max_items", 100))
        if max_items < 1:
            raise ConfigurationError(f"max_items must be positive in source #{index + 1}")
        sources.append(
            RSSSourceConfig(
                name=str(_required(item, "name", f"source #{index + 1}")),
                url=str(_required(item, "url", f"source #{index + 1}")),
                enabled=bool(item.get("enabled", True)),
                tags=tuple(str(tag) for tag in item.get("tags", [])),
                max_items=max_items,
            )
        )

    title_threshold = float(app.get("title_similarity_threshold", 0.92))
    event_threshold = float(app.get("event_similarity_threshold", 0.62))
    if not 0 <= title_threshold <= 1:
        raise ConfigurationError("title_similarity_threshold must be between 0 and 1")
    if not 0 <= event_threshold <= 1:
        raise ConfigurationError("event_similarity_threshold must be between 0 and 1")

    return AppConfig(
        database_path=Path(app.get("database_path", "data/articles.db")),
        reports_dir=Path(app.get("reports_dir", "reports")),
        logs_dir=Path(app.get("logs_dir", "logs")),
        request_timeout_seconds=_positive_int(app, "request_timeout_seconds", 20),
        title_similarity_threshold=title_threshold,
        dedup_lookback_days=_positive_int(app, "dedup_lookback_days", 30),
        processing_batch_size=_positive_int(app, "processing_batch_size", 50),
        report_max_articles=_positive_int(app, "report_max_articles", 100),
        content_timeout_seconds=_positive_int(app, "content_timeout_seconds", 20),
        content_min_length=_positive_int(app, "content_min_length", 200),
        content_max_bytes=_positive_int(app, "content_max_bytes", 5_000_000),
        content_batch_size=_positive_int(app, "content_batch_size", 20),
        event_time_window_days=_positive_int(app, "event_time_window_days", 7),
        event_similarity_threshold=event_threshold,
        event_batch_size=_positive_int(app, "event_batch_size", 500),
        research_top_k=_positive_int(app, "research_top_k", 10),
        prompts_dir=Path(app.get("prompts_dir", "prompts")),
        sources=tuple(source for source in sources if source.enabled),
    )

