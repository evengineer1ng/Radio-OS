# Copilot / AI Agent Instructions — Radio OS

This repo is a desktop-first, content-agnostic "radio" runtime composed of a UI shell, a station runtime engine, and many small feed plugins. Use these notes to be productive quickly when editing, adding plugins, or changing station configuration.

- **Big picture**: `shell.py` is the desktop UI and process manager; `runtime.py` is the station engine that runs feeds, routes events, and exposes runtime globals; per-station entrypoints live under `stations/<station_id>/` (e.g. `algofm.py`). `launcher.py` can spawn a station process with the correct environment.

- **Key env vars and paths**: the runtime and launcher communicate via environment variables. Important ones are `STATION_DIR`, `STATION_DB_PATH`, `STATION_MEMORY_PATH`, `RADIO_OS_ROOT`, `RADIO_OS_PLUGINS`, `RADIO_OS_VOICES`, `CONTEXT_MODEL`, `HOST_MODEL`. `launcher.py` shows an example of how these are set for a station.

- **Plugin contract** (plugins/*.py)
  - Plugins are simple modules under `plugins/`. They are imported dynamically by `runtime.py` and `shell.py`.
  - Feed plugins: provide a `feed_worker` callable and optionally set `IS_FEED = True` (default). `runtime.load_feed_plugins()` expects `feed_worker` to exist.
  - Widget registration: implement `register_widgets(registry, runtime_stub)` to add UI widgets (see `runtime.WIDGETS` and `runtime.runtime_stub`).
  - Module metadata conventions: `PLUGIN_NAME`, `PLUGIN_DESC`, `FEED_DEFAULTS` (or `DEFAULT_FEED_CFG` / `DEFAULT_CONFIG`) are read by the shell.
  - Plugins commonly import `your_runtime` as a shim; the real runtime exposes the same names at runtime (`event_q`, `StationEvent`, `log`, `now_ts`, etc.). See `your_runtime.py` for the compatibility shim.

- **Data & queues**: `runtime.py` exposes several global queues used across components: `event_q`, `ui_q`, `ui_cmd_q`, `dj_q`, `subtitle_q`. Treat these as the primary in-process pub/sub channels.

- **Station manifest**: `stations/<id>/manifest.yaml` drives station-specific configuration (paths, models, pacing). Code that reads it: `runtime.load_station_manifest()` and utilities in `kernel.py` / `shell.py` (see `station_manifest_path`). Keys commonly present: `paths.db`, `paths.memory`, `models.producer_model`, `models.host_model`, and `pacing`.

- **Voices & models**: voice model files live in `voices/` (ONNX files). `runtime.resolve_voice_path()` resolves voice model locations and honors `RADIO_OS_VOICES` / `GLOBAL_VOICES_DIR`.

- **Runtime logs & debugging**:
  - The shell writes station stdout/stderr into `stations/<id>/runtime.log` when launching. `shell.StationProcess.launch()` shows the command used.
  - Run the shell locally for manual testing: `python shell.py` (from repo root / activated virtualenv).
  - To launch a single station like the launcher does, run `python launcher.py` or inspect `launcher.launch_station()` to see environment wiring and the per-station runtime called (e.g. `stations/algotradingfm/algofm.py`).

- **Virtualenv & dependencies**: there is a local virtualenv at `radioenv/`. Use `radioenv\Scripts\Activate.ps1` (PowerShell) or the Activate script in `radioenv\Scripts` on Windows. Install extra packages into that environment; `dependencies.txt` lists extras used by the project.

- **Conventions and patterns to follow**:
  - Plugins: keep plugins small, single-responsibility modules exposing `feed_worker` or `register_widgets` only.
  - Config resolution: prefer `resolve_cfg_path()` and `resolve_voice_path()` when referencing files so station-relative paths and global overrides are respected.
  - Non-blocking: the runtime uses queues and worker-style feed functions; avoid long blocking calls on the main thread — use threads or asyncio if needed and push events onto `event_q`.

- **Examples to inspect when implementing features**:
  - Plugin discovery and metadata: `shell.discover_plugins()` (see how `FEED_DEFAULTS` and `PLUGIN_NAME` are used).
  - Plugin load-time registration: `runtime.load_feed_plugins()` (shows `runtime_stub` that's passed to `register_widgets`).
  - Launcher wiring: `launcher.launch_station()` (example env settings for a station).

- **What not to change lightly**:
  - The names of global queues or `your_runtime` shim — many plugins import these by name.
  - Manifest keys and the paths layout — changing layout requires updating `launcher.py` and `shell.py` launch logic.

If anything in these notes is unclear or you'd like more examples (e.g. a sample plugin skeleton or a checklist for adding a new station), tell me which part to expand and I'll iterate.
