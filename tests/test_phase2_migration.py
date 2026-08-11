from __future__ import annotations

import sqlite3
from pathlib import Path

from app.storage.database import Database


def test_phase1_database_migrates_without_data_loss(tmp_path: Path) -> None:
    path = tmp_path / "phase1.db"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE articles (
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
        INSERT INTO articles (
            title, url, normalized_url, source, collected_at, raw_text, tags,
            normalized_title, processing_status, created_at, updated_at
        ) VALUES (
            'Existing article', 'https://example.com/old', 'https://example.com/old',
            'Test', '2026-08-11T00:00:00+00:00', 'RSS text', '[]',
            'existing article', 'processed', '2026-08-11T00:00:00+00:00',
            '2026-08-11T00:00:00+00:00'
        );
        """
    )
    connection.commit()
    connection.close()

    database = Database(path)
    database.initialize()
    database.initialize()

    with database.connect() as migrated:
        columns = {row["name"] for row in migrated.execute("PRAGMA table_info(articles)")}
        title = migrated.execute("SELECT title FROM articles").fetchone()["title"]
        tables = {
            row["name"]
            for row in migrated.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        versions = [row["version"] for row in migrated.execute("SELECT version FROM schema_migrations")]

    assert title == "Existing article"
    assert {"content", "content_status", "content_length", "content_fetched_at"} <= columns
    assert {"events", "event_articles", "research_briefs", "evaluations"} <= tables
    assert versions == [1, 2]

