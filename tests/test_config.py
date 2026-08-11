from __future__ import annotations

from pathlib import Path

import pytest

from app.config import ConfigurationError, load_config


def test_load_config_filters_disabled_sources(tmp_path: Path) -> None:
    path = tmp_path / "sources.yaml"
    path.write_text(
        """
app:
  title_similarity_threshold: 0.9
sources:
  - name: Enabled
    url: https://example.com/feed
  - name: Disabled
    url: https://example.org/feed
    enabled: false
""",
        encoding="utf-8",
    )
    config = load_config(path)
    assert config.title_similarity_threshold == 0.9
    assert [source.name for source in config.sources] == ["Enabled"]


def test_invalid_threshold_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "invalid.yaml"
    path.write_text(
        "app:\n  title_similarity_threshold: 2\nsources: []\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError):
        load_config(path)

