#!/usr/bin/env python3
"""
KerbalFM Station Entrypoint
=============================
Bootstraps the KSP live commentary station powered by:
  - plugins/ksp_sdk.py      — kRPC telemetry feed (or sim mode if KSP not running)
  - plugins/meta/ksp_meta.py — two-voice LLM commentary (Launch Control + Flight Director)
  - tools/ksp_agent.py       — OpenClaw autonomous AI pilot (run separately)

Usage:
    # Via launcher (recommended):
    python launcher.py KerbalFM

    # Direct:
    python stations/KerbalFM/entrypoint.py

    # With OpenClaw pilot running alongside:
    python tools/ksp_agent.py --mission "orbit Kerbin at 80km" -v
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
