from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

from app.analysis.factory import build_analysis_components
from app.collectors.rss import RSSCollector
from app.config import ConfigurationError, load_config
from app.logging_config import configure_logging
from app.services.deduplicator import Deduplicator
from app.services.pipeline import CollectionPipeline
from app.services.processor import ArticleProcessor
from app.services.reporter import MarkdownReporter
from app.storage.article_repository import ArticleRepository
from app.storage.database import Database

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app",
        description="AI Industry Intelligence Research Agent MVP",
    )
    parser.add_argument(
        "--config",
        default=os.getenv("AI_INTEL_CONFIG_PATH", "config/sources.yaml"),
        help="Path to YAML source configuration",
    )
    parser.add_argument(
        "--log-level",
        default=os.getenv("AI_INTEL_LOG_LEVEL", "INFO"),
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("collect", help="Collect, normalize, deduplicate, and store RSS articles")

    process = subparsers.add_parser("process", help="Classify, score, and summarize pending articles")
    process.add_argument("--limit", type=int, help="Maximum articles to process")
    process.add_argument("--retry-failed", action="store_true", help="Also retry previously failed articles")

    report = subparsers.add_parser("report", help="Generate a Markdown intelligence report")
    report.add_argument("--limit", type=int, help="Maximum articles in the report")

    run = subparsers.add_parser("run", help="Run collect, process, and report in sequence")
    run.add_argument("--limit", type=int, help="Maximum articles to process and report")
    return parser


def _runtime(config_path: str, log_level: str):
    config = load_config(config_path)
    configure_logging(log_level, config.logs_dir)
    database = Database(config.database_path)
    database.initialize()
    repository = ArticleRepository(database)
    return config, repository


def _collect(config, repository) -> int:
    pipeline = CollectionPipeline(
        config=config,
        collector=RSSCollector(config.request_timeout_seconds),
        repository=repository,
        deduplicator=Deduplicator(
            repository,
            config.title_similarity_threshold,
            config.dedup_lookback_days,
        ),
    )
    stats = pipeline.run()
    print(
        "Collection: "
        f"fetched={stats.fetched}, inserted={stats.inserted}, "
        f"duplicate_url={stats.duplicate_url}, duplicate_title={stats.duplicate_title}, "
        f"invalid={stats.invalid}, source_errors={stats.source_errors}"
    )
    return 0 if stats.source_errors < max(len(config.sources), 1) else 1


def _process(config, repository, limit: int | None, retry_failed: bool = False) -> int:
    processor = ArticleProcessor(repository, build_analysis_components())
    processed, failed = processor.process(
        limit=limit or config.processing_batch_size,
        include_failed=retry_failed,
    )
    print(f"Processing: processed={processed}, failed={failed}")
    return 0 if failed == 0 else 1


def _report(config, repository, limit: int | None) -> Path:
    reporter = MarkdownReporter(repository, config.reports_dir)
    path = reporter.generate(limit or config.report_max_articles)
    print(f"Report: {path}")
    return path


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config, repository = _runtime(args.config, args.log_level)
        if args.command == "collect":
            return _collect(config, repository)
        if args.command == "process":
            return _process(config, repository, args.limit, args.retry_failed)
        if args.command == "report":
            _report(config, repository, args.limit)
            return 0
        if args.command == "run":
            collect_code = _collect(config, repository)
            process_code = _process(config, repository, args.limit)
            _report(config, repository, args.limit)
            return max(collect_code, process_code)
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}")
        return 2
    except KeyboardInterrupt:
        print("Interrupted")
        return 130
    except Exception:
        logger.exception("Unexpected application error")
        return 1
    return 0

