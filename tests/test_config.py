"""Tests for configuration management."""

import json

from evergrowth.core.config import (
    EvergrowthConfig,
    load_config,
    save_config,
)


class TestConfig:
    """Test config loading, saving, and defaults."""

    def test_default_config(self):
        """Test default config values."""
        config = EvergrowthConfig()
        assert config.di_name == "Lyra"
        assert config.di_letter == "L"
        assert config.heartbeat.default_interval_minutes == 30
        assert config.memory.db_path == "~/.evergrowth/memory.db"

    def test_load_nonexistent_returns_defaults(self):
        """Test loading a non-existent config returns defaults."""
        config = load_config("/nonexistent/path.json")
        assert config.di_name == "Lyra"

    def test_save_and_load(self, tmp_dir):
        """Test saving and loading config."""
        config_path = tmp_dir / "test_config.json"
        config = EvergrowthConfig(di_name="SavedDI")
        save_config(config, config_path)

        loaded = load_config(config_path)
        assert loaded.di_name == "SavedDI"

    def test_resolve_paths(self, tmp_dir):
        """Test path resolution."""
        config = EvergrowthConfig(data_dir=str(tmp_dir / "data"))
        assert config.resolve_data_dir() == tmp_dir / "data"

    def test_nested_config(self, tmp_dir):
        """Test nested config dataclasses."""
        config_path = tmp_dir / "nested.json"
        data = {
            "di_name": "NestedDI",
            "heartbeat": {
                "enabled": False,
                "default_interval_minutes": 60,
            },
        }
        config_path.write_text(json.dumps(data))

        config = load_config(config_path)
        assert config.di_name == "NestedDI"
        assert config.heartbeat.enabled is False
        assert config.heartbeat.default_interval_minutes == 60
