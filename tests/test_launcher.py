"""
Tests for launcher.py — station launch configuration.
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from launcher import get_global_config_path, get_global_config


class TestGlobalConfig:
    """Tests for global config path resolution."""

    def test_config_path_is_string(self):
        path = get_global_config_path()
        assert isinstance(path, str)
        assert path.endswith("config.json")

    def test_config_path_platform_appropriate(self):
        path = get_global_config_path()
        if sys.platform == "darwin":
            assert ".radioOS" in path
        elif sys.platform == "win32":
            assert "RadioOS" in path
        else:
            assert ".radioOS" in path

    def test_get_global_config_returns_dict(self):
        cfg = get_global_config()
        assert isinstance(cfg, dict)
