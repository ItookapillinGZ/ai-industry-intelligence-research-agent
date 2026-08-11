from __future__ import annotations

from pathlib import Path

import pytest

from app.storage.article_repository import ArticleRepository
from app.storage.database import Database


@pytest.fixture
def repository(tmp_path: Path) -> ArticleRepository:
    database = Database(tmp_path / "test.db")
    database.initialize()
    return ArticleRepository(database)

