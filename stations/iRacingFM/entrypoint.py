#!/usr/bin/env python3
"""
iRacingFM Station Entrypoint
=============================
Bootstraps the iRacing live commentary station.
Called by launcher.py (or directly for dev).

Usage:
    # Via launcher (recommended):
    python launcher.py iRacingFM

    # Direct (set env vars manually first):
    export STATION_DIR=/path/to/stations/iRacingFM
    export STATION_DB_PATH=$STATION_DIR/station.sqlite
    export STATION_MEMORY_PATH=$STATION_DIR/station_memory.json
    export RADIO_OS_ROOT=/path/to/Radio-OS
    export OPENAI_API_KEY=sk-...
    python stations/iRacingFM/entrypoint.py

The station runs bookmark.py's main loop with iRacingFM's manifest.
The live iRacing telemetry feed (plugins/iracing_sdk.py) connects to
the iRacing shared-memory API on Windows, or falls back to simulation
mode on macOS/Linux for development.
"""

import os
import sys

# ── Path setup ──────────────────────────────────────────────────────────────
_HERE        = os.path.dirname(os.path.abspath(__file__))
_STATION_DIR = _HERE
_ROOT        = os.path.abspath(os.path.join(_HERE, "..", ".."))

sys.path.insert(0, _ROOT)

# ── Env defaults (only if not already set by launcher) ──────────────────────
os.environ.setdefault("STATION_DIR",        _STATION_DIR)
os.environ.setdefault("STATION_DB_PATH",    os.path.join(_STATION_DIR, "station.sqlite"))
os.environ.setdefault("STATION_MEMORY_PATH",os.path.join(_STATION_DIR, "station_memory.json"))
os.environ.setdefault("RADIO_OS_ROOT",      _ROOT)
os.environ.setdefault("RADIO_OS_PLUGINS",   os.path.join(_ROOT, "plugins"))
os.environ.setdefault("RADIO_OS_VOICES",    os.path.join(_ROOT, "voices"))

# ── Hand off to bookmark runtime ─────────────────────────────────────────────
import bookmark  # noqa: E402  (must come after path/env setup)

if __name__ == "__main__":
    bookmark.main()
