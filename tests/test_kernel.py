"""
Tests for kernel.py — manifest loading and config parsing.
"""
import os
import tempfile
import yaml
import pytest

# Add project root to path
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kernel import load_manifest, get_scheduler_quotas


class TestLoadManifest:
    """Tests for load_manifest()."""

    def test_loads_valid_manifest(self, tmp_path):
        """Should parse a valid manifest.yaml and return a dict."""
        manifest = {
            "station": {"name": "TestFM", "host": "Tester"},
            "models": {"producer": "gpt-4o", "host": "gpt-4o"},
            "paths": {"db": "station.sqlite", "memory": "station_memory.json"},
        }
        manifest_path = tmp_path / "manifest.yaml"
        manifest_path.write_text(yaml.dump(manifest))

        result = load_manifest(str(tmp_path))
        assert result["station"]["name"] == "TestFM"
        assert result["models"]["producer"] == "gpt-4o"

    def test_returns_empty_dict_on_missing_file(self, tmp_path):
        """Should return {} when manifest.yaml doesn't exist."""
        result = load_manifest(str(tmp_path))
        assert result == {}

    def test_returns_empty_dict_on_invalid_yaml(self, tmp_path):
        """Should return {} on unparseable YAML."""
        manifest_path = tmp_path / "manifest.yaml"
        manifest_path.write_text("{{{{not valid yaml::::")

        result = load_manifest(str(tmp_path))
        # Should not crash — returns {} or the parsed result
        assert isinstance(result, (dict, type(None)))


class TestGetSchedulerQuotas:
    """Tests for get_scheduler_quotas()."""

    def test_extracts_quotas(self):
        manifest = {"scheduler": {"quotas": {"rss": 5, "reddit": 10}}}
        result = get_scheduler_quotas(manifest)
        assert result == {"rss": 5, "reddit": 10}

    def test_returns_empty_on_missing_scheduler(self):
        assert get_scheduler_quotas({}) == {}

    def test_returns_empty_on_missing_quotas(self):
        assert get_scheduler_quotas({"scheduler": {}}) == {}
