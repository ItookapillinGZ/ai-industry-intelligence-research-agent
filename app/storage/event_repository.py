from __future__ import annotations

from sqlite3 import Row

from app.models import Event, StoredArticle, utc_now_iso
from app.storage.article_repository import article_from_row
from app.storage.database import Database


def event_from_row(row: Row) -> Event:
    return Event(
        id=row["id"],
        title=row["title"],
        normalized_title=row["normalized_title"],
        category=row["category"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        importance_score=float(row["importance_score"] or 0),
        article_count=int(row["article_count"] or 0),
        source_count=int(row["source_count"] or 0),
    )


class EventRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def list_ungrouped_articles(self, limit: int) -> list[StoredArticle]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT a.* FROM articles a
                LEFT JOIN event_articles ea ON ea.article_id = a.id
                WHERE a.processing_status = 'processed' AND ea.article_id IS NULL
                ORDER BY COALESCE(a.published_at, a.collected_at) DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [article_from_row(row) for row in rows]

    def create_event(self, article: StoredArticle) -> Event:
        now = utc_now_iso()
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO events (
                    title, normalized_title, category, created_at, updated_at,
                    importance_score, article_count, source_count
                ) VALUES (?, ?, ?, ?, ?, ?, 0, 0)
                """,
                (
                    article.title,
                    article.normalized_title,
                    article.category or "Other",
                    now,
                    now,
                    float(article.importance_score or 0),
                ),
            )
            row = connection.execute("SELECT * FROM events WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return event_from_row(row)

    def link_article(self, event_id: int, article_id: int, similarity_score: float) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO event_articles (event_id, article_id, similarity_score, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (event_id, article_id, similarity_score, utc_now_iso()),
            )

    def update_metrics(self, event_id: int) -> Event:
        with self.database.connect() as connection:
            metrics = connection.execute(
                """
                SELECT COUNT(*) AS article_count,
                       COUNT(DISTINCT a.source) AS source_count,
                       COALESCE(MAX(a.importance_score), 0) AS max_score
                FROM event_articles ea
                JOIN articles a ON a.id = ea.article_id
                WHERE ea.event_id = ?
                """,
                (event_id,),
            ).fetchone()
            connection.execute(
                """
                UPDATE events
                SET article_count = ?, source_count = ?, importance_score = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    metrics["article_count"],
                    metrics["source_count"],
                    metrics["max_score"],
                    utc_now_iso(),
                    event_id,
                ),
            )
            row = connection.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
        return event_from_row(row)

    def update_importance(self, event_id: int, score: float) -> None:
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE events SET importance_score = ?, updated_at = ? WHERE id = ?",
                (max(0.0, min(10.0, score)), utc_now_iso(), event_id),
            )

    def get(self, event_id: int) -> Event | None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
        return event_from_row(row) if row else None

    def list_events(self, limit: int | None = None) -> list[Event]:
        sql = "SELECT * FROM events ORDER BY importance_score DESC, updated_at DESC"
        parameters: tuple[object, ...] = ()
        if limit is not None:
            sql += " LIMIT ?"
            parameters = (limit,)
        with self.database.connect() as connection:
            rows = connection.execute(sql, parameters).fetchall()
        return [event_from_row(row) for row in rows]

    def list_articles(self, event_id: int) -> list[StoredArticle]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT a.* FROM articles a
                JOIN event_articles ea ON ea.article_id = a.id
                WHERE ea.event_id = ?
                ORDER BY a.importance_score DESC, COALESCE(a.published_at, a.collected_at) DESC
                """,
                (event_id,),
            ).fetchall()
        return [article_from_row(row) for row in rows]

    def count(self) -> int:
        with self.database.connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM events").fetchone()
        return int(row["count"])

