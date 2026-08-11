from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _ensure_column(
        connection: sqlite3.Connection,
        table: str,
        column: str,
        definition: str,
    ) -> None:
        columns = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    description TEXT NOT NULL,
                    applied_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS articles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    normalized_url TEXT NOT NULL UNIQUE,
                    source TEXT NOT NULL,
                    author TEXT,
                    published_at TEXT,
                    collected_at TEXT NOT NULL,
                    raw_text TEXT NOT NULL DEFAULT '',
                    summary TEXT,
                    category TEXT,
                    importance_score REAL,
                    tags TEXT NOT NULL DEFAULT '[]',
                    normalized_title TEXT NOT NULL,
                    processing_status TEXT NOT NULL DEFAULT 'pending',
                    llm_provider TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    content TEXT,
                    content_status TEXT NOT NULL DEFAULT 'pending',
                    content_length INTEGER NOT NULL DEFAULT 0,
                    content_fetched_at TEXT,
                    content_error TEXT
                );
                """
            )

            self._ensure_column(connection, "articles", "content", "TEXT")
            self._ensure_column(
                connection, "articles", "content_status", "TEXT NOT NULL DEFAULT 'pending'"
            )
            self._ensure_column(
                connection, "articles", "content_length", "INTEGER NOT NULL DEFAULT 0"
            )
            self._ensure_column(connection, "articles", "content_fetched_at", "TEXT")
            self._ensure_column(connection, "articles", "content_error", "TEXT")

            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    normalized_title TEXT NOT NULL,
                    category TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    importance_score REAL NOT NULL DEFAULT 0,
                    article_count INTEGER NOT NULL DEFAULT 0,
                    source_count INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS event_articles (
                    event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
                    article_id INTEGER NOT NULL UNIQUE REFERENCES articles(id) ON DELETE CASCADE,
                    similarity_score REAL NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (event_id, article_id)
                );

                CREATE TABLE IF NOT EXISTS research_briefs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id INTEGER NOT NULL UNIQUE REFERENCES events(id) ON DELETE CASCADE,
                    headline TEXT NOT NULL,
                    executive_summary TEXT NOT NULL,
                    what_happened TEXT NOT NULL,
                    key_facts TEXT NOT NULL DEFAULT '[]',
                    background TEXT NOT NULL,
                    why_it_matters TEXT NOT NULL,
                    industry_impact TEXT NOT NULL,
                    ugc_relevance TEXT NOT NULL,
                    evidence TEXT NOT NULL DEFAULT '[]',
                    sources TEXT NOT NULL DEFAULT '[]',
                    uncertainties TEXT NOT NULL DEFAULT '[]',
                    confidence REAL NOT NULL,
                    tags TEXT NOT NULL DEFAULT '[]',
                    provider_name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS evaluations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    research_brief_id INTEGER NOT NULL REFERENCES research_briefs(id) ON DELETE CASCADE,
                    evaluator TEXT NOT NULL,
                    factuality INTEGER NOT NULL CHECK (factuality BETWEEN 1 AND 5),
                    source_coverage INTEGER NOT NULL CHECK (source_coverage BETWEEN 1 AND 5),
                    relevance INTEGER NOT NULL CHECK (relevance BETWEEN 1 AND 5),
                    insightfulness INTEGER NOT NULL CHECK (insightfulness BETWEEN 1 AND 5),
                    clarity INTEGER NOT NULL CHECK (clarity BETWEEN 1 AND 5),
                    notes TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_articles_normalized_title
                    ON articles(normalized_title);
                CREATE INDEX IF NOT EXISTS idx_articles_collected_at
                    ON articles(collected_at DESC);
                CREATE INDEX IF NOT EXISTS idx_articles_processing_status
                    ON articles(processing_status);
                CREATE INDEX IF NOT EXISTS idx_articles_content_status
                    ON articles(content_status);
                CREATE INDEX IF NOT EXISTS idx_articles_importance
                    ON articles(importance_score DESC);
                CREATE INDEX IF NOT EXISTS idx_events_importance
                    ON events(importance_score DESC);
                CREATE INDEX IF NOT EXISTS idx_event_articles_event
                    ON event_articles(event_id);
                CREATE INDEX IF NOT EXISTS idx_evaluations_brief
                    ON evaluations(research_brief_id);
                """
            )
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations VALUES (1, 'phase 1 base schema', datetime('now'))"
            )
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations VALUES (2, 'phase 2 research workflow', datetime('now'))"
            )

