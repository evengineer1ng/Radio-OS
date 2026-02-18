"""
Tests for your_runtime.py — the plugin compatibility shim.
"""
import os
import sys
import time
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from your_runtime import now_ts, log, get_visual_model_config


class TestNowTs:
    """Tests for the now_ts() timestamp helper."""

    def test_returns_int(self):
        assert isinstance(now_ts(), int)

    def test_returns_current_epoch(self):
        ts = now_ts()
        assert abs(ts - int(time.time())) <= 1


class TestLog:
    """Tests for the log() shim."""

    def test_single_arg_call(self, capsys):
        log("hello world")
        captured = capsys.readouterr()
        assert "hello world" in captured.out

    def test_two_arg_call(self, capsys):
        log("FEED", "got 5 items")
        captured = capsys.readouterr()
        assert "FEED" in captured.out
        assert "got 5 items" in captured.out


class TestGetVisualModelConfig:
    """Tests for visual model config env var parsing."""

    def test_defaults_when_no_env(self, monkeypatch):
        # Clear any visual model env vars
        for key in [
            "VISUAL_MODEL_TYPE", "VISUAL_MODEL_LOCAL",
            "VISUAL_MODEL_API_PROVIDER", "VISUAL_MODEL_API_MODEL",
            "VISUAL_MODEL_API_KEY", "VISUAL_MODEL_API_ENDPOINT",
            "VISUAL_MODEL_MAX_IMAGE_SIZE", "VISUAL_MODEL_IMAGE_QUALITY",
        ]:
            monkeypatch.delenv(key, raising=False)

        cfg = get_visual_model_config()
        assert cfg["model_type"] == "local"
        assert cfg["max_image_size"] == 1024
        assert cfg["image_quality"] == 85

    def test_reads_env_vars(self, monkeypatch):
        monkeypatch.setenv("VISUAL_MODEL_TYPE", "api")
        monkeypatch.setenv("VISUAL_MODEL_API_PROVIDER", "openai")
        monkeypatch.setenv("VISUAL_MODEL_MAX_IMAGE_SIZE", "512")

        cfg = get_visual_model_config()
        assert cfg["model_type"] == "api"
        assert cfg["api_provider"] == "openai"
        assert cfg["max_image_size"] == 512
