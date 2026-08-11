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

    def initialize(self) -> None:
        schema = """
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
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_articles_normalized_title
            ON articles(normalized_title);
        CREATE INDEX IF NOT EXISTS idx_articles_collected_at
            ON articles(collected_at DESC);
        CREATE INDEX IF NOT EXISTS idx_articles_processing_status
            ON articles(processing_status);
        CREATE INDEX IF NOT EXISTS idx_articles_importance
            ON articles(importance_score DESC);
        """
        with self.connect() as connection:
            connection.executescript(schema)

