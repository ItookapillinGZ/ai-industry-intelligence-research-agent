from __future__ import annotations

import json
from dataclasses import asdict

from app.models import EvidenceItem, EvidencePack, utc_now_iso
from app.storage.database import Database


def _pack_from_row(row) -> EvidencePack:
    return EvidencePack(
        id=row["id"],
        event_id=row["event_id"],
        mode=row["mode"],
        queries=json.loads(row["queries"] or "[]"),
        items=[EvidenceItem(**item) for item in json.loads(row["items"] or "[]")],
        coverage_status=row["coverage_status"],
        coverage_note=row["coverage_note"],
        errors=json.loads(row["errors"] or "[]"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class EvidencePackRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def save(self, pack: EvidencePack) -> EvidencePack:
        now = utc_now_iso()
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO evidence_packs (
                    event_id, mode, queries, items, coverage_status, coverage_note,
                    errors, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id, mode) DO UPDATE SET
                    queries = excluded.queries,
                    items = excluded.items,
                    coverage_status = excluded.coverage_status,
                    coverage_note = excluded.coverage_note,
                    errors = excluded.errors,
                    updated_at = excluded.updated_at
                """,
                (
                    pack.event_id,
                    pack.mode,
                    json.dumps(pack.queries, ensure_ascii=False),
                    json.dumps([asdict(item) for item in pack.items], ensure_ascii=False),
                    pack.coverage_status,
                    pack.coverage_note,
                    json.dumps(pack.errors, ensure_ascii=False),
                    pack.created_at or now,
                    now,
                ),
            )
            row = connection.execute(
                "SELECT * FROM evidence_packs WHERE event_id = ? AND mode = ?",
                (pack.event_id, pack.mode),
            ).fetchone()
        return _pack_from_row(row)

    def get(self, event_id: int, mode: str) -> EvidencePack | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM evidence_packs WHERE event_id = ? AND mode = ?",
                (event_id, mode),
            ).fetchone()
        return _pack_from_row(row) if row else None

    def list_for_events(self, event_ids: list[int], mode: str) -> list[EvidencePack]:
        if not event_ids:
            return []
        placeholders = ",".join("?" for _ in event_ids)
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM evidence_packs
                WHERE mode = ? AND event_id IN ({placeholders})
                ORDER BY event_id
                """,
                (mode, *event_ids),
            ).fetchall()
        return [_pack_from_row(row) for row in rows]

    def count(self, mode: str | None = None) -> int:
        sql = "SELECT COUNT(*) AS count FROM evidence_packs"
        parameters: tuple[object, ...] = ()
        if mode:
            sql += " WHERE mode = ?"
            parameters = (mode,)
        with self.database.connect() as connection:
            row = connection.execute(sql, parameters).fetchone()
        return int(row["count"])
