from __future__ import annotations

from pathlib import Path

from app.config import load_config


def test_source_max_items_is_configurable(tmp_path: Path) -> None:
    path = tmp_path / "sources.yaml"
    path.write_text(
        "sources:\n  - name: Limited\n    url: https://example.com/feed\n    max_items: 25\n",
        encoding="utf-8",
    )
    config = load_config(path)
    assert config.sources[0].max_items == 25
