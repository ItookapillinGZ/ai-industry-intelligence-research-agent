from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

from app.analysis.factory import build_analysis_components
from app.analysis.taxonomy_service import TaxonomyService
from app.collectors.rss import RSSCollector
from app.config import ConfigurationError, load_config
from app.content.service import ContentExtractionService
from app.content.trafilatura_extractor import TrafilaturaContentExtractor
from app.evaluation.reporter import EvaluationReportGenerator
from app.evaluation.comparison_reporter import ResearchComparisonReportGenerator
from app.evaluation.template import ResearchEvaluationTemplateGenerator
from app.evaluation.service import EvaluationService
from app.events.grouping import DeterministicEventGrouper
from app.events.importance import AuditableEventScorer
from app.events.audit_reporter import RankingAuditReportGenerator
from app.events.service import EventGroupingService, EventRankingService
from app.logging_config import configure_logging
from app.research.factory import build_research_workflow
from app.research.reporter import ResearchReportGenerator
from app.research.service import ResearchService
from app.services.deduplicator import Deduplicator
from app.services.pipeline import CollectionPipeline
from app.services.processor import ArticleProcessor
from app.services.reporter import MarkdownReporter
from app.storage.article_repository import ArticleRepository
from app.storage.database import Database
from app.storage.evaluation_repository import EvaluationRepository
from app.storage.event_repository import EventRepository
from app.storage.research_repository import ResearchRepository
from app.storage.evidence_repository import EvidencePackRepository

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app",
        description="AI Industry Intelligence Research Agent",
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
    process.add_argument("--retry-failed", action="store_true", help="Also retry failed articles")

    report = subparsers.add_parser("report", help="Generate the Phase 1 article report")
    report.add_argument("--limit", type=int, help="Maximum articles in the report")

    run = subparsers.add_parser("run", help="Run the Phase 1 collect, process, and report sequence")
    run.add_argument("--limit", type=int, help="Maximum articles to process and report")

    content = subparsers.add_parser("fetch-content", help="Fetch and extract full article text")
    content.add_argument("--limit", type=int, help="Maximum articles to fetch")
    content.add_argument("--retry-failed", action="store_true", help="Retry failed content fetches")

    events = subparsers.add_parser("events", help="Group articles into events and rank Top-K")
    events.add_argument("--limit", type=int, help="Maximum ungrouped articles to consider")
    events.add_argument("--top", type=int, help="Number of ranked events to display")

    research = subparsers.add_parser("research", help="Generate ResearchBrief records for Top-K events")
    research.add_argument("--top", type=int, help="Number of events to research")
    research.add_argument(
        "--mode",
        choices=("deterministic", "single-source-llm", "multi-source-llm"),
        default="deterministic",
        help="Research mode; LLM modes are explicitly marked fallback when no API key exists",
    )
    research.add_argument("--force", action="store_true", help="Regenerate existing briefs")

    research_report = subparsers.add_parser(
        "research-report", help="Generate the Phase 2 Research Intelligence Report"
    )
    research_report.add_argument("--top", type=int, help="Maximum researched events in the report")
    research_report.add_argument(
        "--mode",
        choices=("deterministic", "single-source-llm", "multi-source-llm"),
        default="deterministic",
    )

    evaluate = subparsers.add_parser(
        "evaluate", help="Import human evaluation JSON and generate a Markdown summary"
    )
    evaluate.add_argument("--input", type=Path, required=True, help="Evaluation JSON file")


    reclassify = subparsers.add_parser(
        "reclassify", help="Apply the Phase 2.5 category taxonomy to processed articles"
    )
    reclassify.add_argument("--limit", type=int, default=1000)

    gather = subparsers.add_parser(
        "gather-evidence", help="Gather and save multi-source Evidence Packs for Top-K events"
    )
    gather.add_argument("--top", type=int, help="Number of events")

    template = subparsers.add_parser(
        "evaluation-template", help="Create a three-mode human evaluation template"
    )
    template.add_argument("--top", type=int, default=10)

    comparison = subparsers.add_parser(
        "comparison-report", help="Generate the Phase 2.5 research comparison report"
    )
    comparison.add_argument("--top", type=int, default=10)

    ranking_audit = subparsers.add_parser(
        "ranking-audit", help="Generate the eight-dimension ranking audit report"
    )
    ranking_audit.add_argument("--top", type=int, default=10)

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
    path = MarkdownReporter(repository, config.reports_dir).generate(
        limit or config.report_max_articles
    )
    print(f"Report: {path}")
    return path


def _fetch_content(config, repository, limit: int | None, retry_failed: bool) -> int:
    extractor = TrafilaturaContentExtractor(
        timeout_seconds=config.content_timeout_seconds,
        min_length=config.content_min_length,
        max_bytes=config.content_max_bytes,
    )
    stats = ContentExtractionService(repository, extractor).fetch(
        limit or config.content_batch_size,
        include_failed=retry_failed,
    )
    print(
        f"Content: attempted={stats.attempted}, fetched={stats.fetched}, "
        f"failed={stats.failed}, skipped={stats.skipped}"
    )
    return 0


def _events(config, repository, limit: int | None, top: int | None) -> int:
    event_repository = EventRepository(repository.database)
    grouping = EventGroupingService(
        event_repository,
        DeterministicEventGrouper(config.event_time_window_days),
        config.event_similarity_threshold,
    ).group(limit or config.event_batch_size)
    ranked = EventRankingService(event_repository, AuditableEventScorer()).rank(
        top or config.research_top_k
    )
    print(
        f"Events: considered={grouping.articles_considered}, created={grouping.events_created}, "
        f"linked={grouping.articles_linked}, total={event_repository.count()}"
    )
    for index, event in enumerate(ranked, 1):
        print(
            f"{index}. event_id={event.id} score={event.importance_score:.2f} "
            f"articles={event.article_count} sources={event.source_count} title={event.title}"
        )
    return 0


def _research(config, repository, top: int | None, force: bool, mode: str) -> int:
    event_repository = EventRepository(repository.database)
    EventRankingService(event_repository, AuditableEventScorer()).rank(
        top or config.research_top_k
    )
    stats = ResearchService(
        event_repository,
        ResearchRepository(repository.database),
        build_research_workflow(
            mode,
            config.prompts_dir,
            repository.database,
            search_timeout_seconds=config.request_timeout_seconds,
        ),
    ).research_top_events(top or config.research_top_k, force=force)
    print(
        f"Research: considered={stats.considered}, generated={stats.generated}, "
        f"skipped={stats.skipped}, failed={stats.failed}"
    )
    return 0 if stats.failed == 0 else 1


def _research_report(config, repository, top: int | None, mode: str) -> Path:
    path = ResearchReportGenerator(
        ResearchRepository(repository.database), config.reports_dir
    ).generate(top or config.research_top_k, mode.replace("-", "_"))
    print(f"Research report: {path}")
    return path


def _evaluate(config, repository, input_path: Path) -> Path:
    evaluation_repository = EvaluationRepository(repository.database)
    saved = EvaluationService(evaluation_repository).import_file(input_path)
    path = EvaluationReportGenerator(evaluation_repository, config.reports_dir).generate()
    print(f"Evaluation: imported={len(saved)}, report={path}")
    return path


def _reclassify(config, repository, limit: int) -> int:
    event_repository = EventRepository(repository.database)
    stats = TaxonomyService(repository, event_repository).reclassify(limit)
    EventRankingService(event_repository, AuditableEventScorer()).rank(config.research_top_k)
    print(f"Taxonomy: considered={stats.considered}, changed={stats.changed}")
    return 0


def _gather_evidence(config, repository, top: int | None) -> int:
    from app.evidence.gatherers import BingNewsSearchClient, SearchEvidenceGatherer

    event_repository = EventRepository(repository.database)
    events = EventRankingService(event_repository, AuditableEventScorer()).rank(
        top or config.research_top_k
    )
    gatherer = SearchEvidenceGatherer(
        BingNewsSearchClient(timeout_seconds=config.request_timeout_seconds)
    )
    evidence_repository = EvidencePackRepository(repository.database)
    sufficient = 0
    failed_searches = 0
    for event in events:
        pack = evidence_repository.save(
            gatherer.gather(event, event_repository.list_articles(event.id))
        )
        sufficient += int(pack.coverage_status == "sufficient")
        failed_searches += len(pack.errors)
    print(
        f"Evidence: events={len(events)}, sufficient={sufficient}, "
        f"insufficient={len(events) - sufficient}, search_errors={failed_searches}"
    )
    return 0


def _live_llm_configured() -> bool:
    choice = os.getenv("AI_INTEL_LLM_PROVIDER", "disabled").strip().lower()
    return (
        choice in {"openai", "openai_compatible", "openai-compatible"}
        and bool(os.getenv("AI_INTEL_LLM_API_KEY", "").strip())
    )


def _evaluation_template(config, repository, top: int) -> Path:
    path = ResearchEvaluationTemplateGenerator(
        EventRepository(repository.database),
        ResearchRepository(repository.database),
        Path("evaluation"),
        live_llm_configured=_live_llm_configured(),
    ).generate(top)
    print(f"Evaluation template: {path}")
    return path


def _comparison_report(config, repository, top: int) -> Path:
    path = ResearchComparisonReportGenerator(
        ResearchRepository(repository.database),
        EvaluationRepository(repository.database),
        config.reports_dir,
    ).generate(top)
    print(f"Comparison report: {path}")
    return path


def _ranking_audit(config, repository, top: int) -> Path:
    event_repository = EventRepository(repository.database)
    EventRankingService(event_repository, AuditableEventScorer()).rank(top)
    path = RankingAuditReportGenerator(
        event_repository,
        config.reports_dir,
    ).generate(top)
    print(f"Ranking audit: {path}")
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
        if args.command == "fetch-content":
            return _fetch_content(config, repository, args.limit, args.retry_failed)
        if args.command == "events":
            return _events(config, repository, args.limit, args.top)
        if args.command == "research":
            return _research(config, repository, args.top, args.force, args.mode)
        if args.command == "research-report":
            _research_report(config, repository, args.top, args.mode)
            return 0
        if args.command == "evaluate":
            _evaluate(config, repository, args.input)
            return 0
        if args.command == "reclassify":
            return _reclassify(config, repository, args.limit)
        if args.command == "gather-evidence":
            return _gather_evidence(config, repository, args.top)
        if args.command == "evaluation-template":
            _evaluation_template(config, repository, args.top)
            return 0
        if args.command == "comparison-report":
            _comparison_report(config, repository, args.top)
            return 0
        if args.command == "ranking-audit":
            _ranking_audit(config, repository, args.top)
            return 0

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

