"""
Tests for plugin contract compliance.

Ensures all *top-level* plugins in plugins/ follow the expected contract:
- Have PLUGIN_NAME
- Have IS_FEED
- Feed plugins have feed_worker()
- Non-feed plugins have register_widgets() or a server entry point

Files that declare neither PLUGIN_NAME nor IS_FEED are treated as internal
library/support modules (e.g. name generators, DB layers, UI component
libraries, data templates) and are skipped for contract checks but still
verified to be valid Python via syntax check.
"""
import os
import sys
import ast
import pytest

PLUGINS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "plugins")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _read_source(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


def _is_top_level_plugin(source):
    """A top-level plugin declares at least one of PLUGIN_NAME or IS_FEED."""
    return "PLUGIN_NAME" in source or "IS_FEED" in source


def _list_plugin_files():
    """Return list of .py files in plugins/ (not __init__, not __pycache__)."""
    files = []
    for fname in sorted(os.listdir(PLUGINS_DIR)):
        if fname.endswith(".py") and not fname.startswith("_"):
            files.append(fname)
    return files


def _list_top_level_plugins():
    """Return only files that look like actual plugins (have PLUGIN_NAME or IS_FEED)."""
    result = []
    for fname in _list_plugin_files():
        source = _read_source(os.path.join(PLUGINS_DIR, fname))
        if _is_top_level_plugin(source):
            result.append(fname)
    return result


# ---------------------------------------------------------------------------
# Contract tests — only run on top-level plugins
# ---------------------------------------------------------------------------

class TestPluginContracts:
    """Verify top-level plugins declare required metadata."""

    @pytest.fixture(params=_list_top_level_plugins())
    def plugin_source(self, request):
        filepath = os.path.join(PLUGINS_DIR, request.param)
        return request.param, _read_source(filepath)

    def test_has_plugin_name(self, plugin_source):
        filename, source = plugin_source
        assert "PLUGIN_NAME" in source, (
            f"{filename} is missing PLUGIN_NAME constant"
        )

    def test_has_is_feed(self, plugin_source):
        filename, source = plugin_source
        assert "IS_FEED" in source, (
            f"{filename} is missing IS_FEED constant"
        )

    def test_feed_plugins_have_feed_worker(self, plugin_source):
        filename, source = plugin_source
        if "IS_FEED = True" in source or "IS_FEED=True" in source:
            assert "def feed_worker" in source, (
                f"{filename} declares IS_FEED=True but has no feed_worker()"
            )

    def test_non_feed_plugins_have_register_widgets(self, plugin_source):
        filename, source = plugin_source
        if "IS_FEED = False" in source or "IS_FEED=False" in source:
            has_widgets = "def register_widgets" in source
            has_server = "def start_" in source or "server" in filename.lower()
            assert has_widgets or has_server, (
                f"{filename} declares IS_FEED=False but has neither "
                f"register_widgets() nor a server entry point"
            )


# ---------------------------------------------------------------------------
# Syntax check — every .py file (including library modules) must parse
# ---------------------------------------------------------------------------

class TestPluginSyntax:
    """Verify every .py in plugins/ is syntactically valid Python."""

    @pytest.fixture(params=_list_plugin_files())
    def plugin_file(self, request):
        filepath = os.path.join(PLUGINS_DIR, request.param)
        return request.param, filepath

    def test_valid_python_syntax(self, plugin_file):
        filename, filepath = plugin_file
        source = _read_source(filepath)
        try:
            ast.parse(source, filename=filename)
        except SyntaxError as exc:
            pytest.fail(f"{filename} has a syntax error: {exc}")
