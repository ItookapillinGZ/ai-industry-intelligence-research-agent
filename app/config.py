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
    sources: tuple[RSSSourceConfig, ...] = field(default_factory=tuple)


def _required(mapping: dict[str, Any], key: str, context: str) -> Any:
    value = mapping.get(key)
    if value is None or value == "":
        raise ConfigurationError(f"Missing required field '{key}' in {context}")
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

    threshold = float(app.get("title_similarity_threshold", 0.92))
    if not 0 <= threshold <= 1:
        raise ConfigurationError("title_similarity_threshold must be between 0 and 1")

    return AppConfig(
        database_path=Path(app.get("database_path", "data/articles.db")),
        reports_dir=Path(app.get("reports_dir", "reports")),
        logs_dir=Path(app.get("logs_dir", "logs")),
        request_timeout_seconds=int(app.get("request_timeout_seconds", 20)),
        title_similarity_threshold=threshold,
        dedup_lookback_days=int(app.get("dedup_lookback_days", 30)),
        processing_batch_size=int(app.get("processing_batch_size", 50)),
        report_max_articles=int(app.get("report_max_articles", 100)),
        sources=tuple(source for source in sources if source.enabled),
    )

