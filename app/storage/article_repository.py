from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from sqlite3 import Row

from app.models import ClassificationResult, NormalizedArticle, StoredArticle, utc_now_iso
from app.storage.database import Database


def _from_row(row: Row) -> StoredArticle:
    return StoredArticle(
        id=row["id"],
        title=row["title"],
        url=row["url"],
        source=row["source"],
        author=row["author"],
        published_at=row["published_at"],
        collected_at=row["collected_at"],
        raw_text=row["raw_text"],
        summary=row["summary"],
        category=row["category"],
        importance_score=row["importance_score"],
        tags=json.loads(row["tags"] or "[]"),
        normalized_url=row["normalized_url"],
        normalized_title=row["normalized_title"],
        processing_status=row["processing_status"],
        llm_provider=row["llm_provider"],
    )


class ArticleRepository:
    def __init__(self, database: Database) -> None:
        self.database = database
        self._normalized_url_cache: set[str] | None = None
        self._recent_title_caches: dict[int, list[tuple[int, str, str]]] = {}

    def insert(self, normalized: NormalizedArticle) -> int:
        article = normalized.article
        now = utc_now_iso()
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO articles (
                    title, url, normalized_url, source, author, published_at,
                    collected_at, raw_text, tags, normalized_title, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    article.title,
                    article.url,
                    normalized.normalized_url,
                    article.source,
                    article.author,
                    article.published_at,
                    article.collected_at,
                    article.raw_text,
                    json.dumps(article.tags, ensure_ascii=False),
                    normalized.normalized_title,
                    now,
                    now,
                ),
            )
            article_id = int(cursor.lastrowid)

        if self._normalized_url_cache is not None:
            self._normalized_url_cache.add(normalized.normalized_url)
        for titles in self._recent_title_caches.values():
            titles.append((article_id, article.title, normalized.normalized_title))
        return article_id

    def exists_by_url(self, normalized_url: str) -> bool:
        if self._normalized_url_cache is None:
            with self.database.connect() as connection:
                rows = connection.execute("SELECT normalized_url FROM articles").fetchall()
            self._normalized_url_cache = {str(row["normalized_url"]) for row in rows}
        return normalized_url in self._normalized_url_cache

    def recent_titles(self, lookback_days: int) -> list[tuple[int, str, str]]:
        cached = self._recent_title_caches.get(lookback_days)
        if cached is not None:
            return cached

        cutoff = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).isoformat()
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, title, normalized_title
                FROM articles
                WHERE collected_at >= ?
                """,
                (cutoff,),
            ).fetchall()
        titles = [(row["id"], row["title"], row["normalized_title"]) for row in rows]
        self._recent_title_caches[lookback_days] = titles
        return titles

    def list_pending(self, limit: int, include_failed: bool = False) -> list[StoredArticle]:
        statuses = ("pending", "failed") if include_failed else ("pending",)
        placeholders = ",".join("?" for _ in statuses)
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM articles
                WHERE processing_status IN ({placeholders})
                ORDER BY COALESCE(published_at, collected_at) DESC
                LIMIT ?
                """,
                (*statuses, limit),
            ).fetchall()
        return [_from_row(row) for row in rows]

    def update_analysis(
        self,
        article_id: int,
        classification: ClassificationResult,
        score: float,
        summary: str,
        tags: list[str],
        provider_name: str,
    ) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE articles
                SET summary = ?, category = ?, importance_score = ?, tags = ?,
                    processing_status = 'processed', llm_provider = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    summary,
                    classification.category,
                    max(0.0, min(10.0, score)),
                    json.dumps(tags, ensure_ascii=False),
                    provider_name,
                    utc_now_iso(),
                    article_id,
                ),
            )

    def mark_failed(self, article_id: int) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE articles
                SET processing_status = 'failed', updated_at = ?
                WHERE id = ?
                """,
                (utc_now_iso(), article_id),
            )

    def list_for_report(self, limit: int) -> list[StoredArticle]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM articles
                WHERE processing_status = 'processed'
                ORDER BY importance_score DESC, COALESCE(published_at, collected_at) DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [_from_row(row) for row in rows]

    def count(self) -> int:
        with self.database.connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM articles").fetchone()
        return int(row["count"])
