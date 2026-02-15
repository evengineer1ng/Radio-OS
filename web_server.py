#!/usr/bin/env python3
"""
Radio OS Web Server — Tailscale-accessible web shell.

Serves a web version of shell_bookmark's station browser.
Each station launch spawns a headless bookmark.py runtime on the backend.
The "Web UI" button opens a station runtime dashboard (/runtime/<id>)
which mirrors the tkinter StationUI: live log, audio player, subtitles.
Plugin web servers (FTB, etc.) are proxied through /station/<id>/<path>.
Audio is streamed to web clients via WebSocket.

Can be launched from:
  1. shell_bookmark.py "Launch Server" button
  2. Global setting "always_launch_server"
  3. Standalone: python web_server.py
"""

import asyncio
import io
import json
import os
import signal
import socket
import struct
import subprocess
import sys
import threading
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# ─── Lazy imports ──────────────────────────────────────────────────────────
_fastapi = None
_uvicorn = None

def _ensure_imports():
    global _fastapi, _uvicorn
    if _fastapi is None:
        import fastapi
        _fastapi = fastapi
    if _uvicorn is None:
        import uvicorn
        _uvicorn = uvicorn

# ─── Paths ─────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIONS_DIR = os.path.join(BASE_DIR, "stations")
RUNTIME_PATH = os.path.join(BASE_DIR, "bookmark.py")
PLUGINS_DIR = os.path.join(BASE_DIR, "plugins")
META_PLUGINS_DIR = os.path.join(PLUGINS_DIR, "meta")
VOICES_DIR = os.path.join(BASE_DIR, "voices")

# ─── Config helpers (same as shell_bookmark.py) ────────────────────────────
def get_global_config_path() -> str:
    if os.name == "nt":
        appdata = os.getenv("APPDATA", os.path.expanduser("~"))
        cfg_dir = os.path.join(appdata, "RadioOS")
    else:
        cfg_dir = os.path.expanduser("~/.radioOS")
    os.makedirs(cfg_dir, exist_ok=True)
    return os.path.join(cfg_dir, "config.json")

def get_global_config() -> dict:
    path = get_global_config_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_global_config(cfg: dict):
    path = get_global_config_path()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    os.replace(tmp, path)

# ─── Station discovery (mirrors shell_bookmark.py) ─────────────────────────
import yaml

def discover_stations() -> List[Dict[str, Any]]:
    """Return list of station info dicts."""
    stations = []
    if not os.path.isdir(STATIONS_DIR):
        return stations
    for name in sorted(os.listdir(STATIONS_DIR)):
        path = os.path.join(STATIONS_DIR, name)
        if not os.path.isdir(path):
            continue
        mp = os.path.join(path, "manifest.yaml")
        if not os.path.exists(mp):
            continue
        try:
            with open(mp, "r", encoding="utf-8") as f:
                manifest = yaml.safe_load(f) or {}
        except Exception:
            manifest = {}
        stations.append({
            "station_id": name,
            "path": path,
            "name": (manifest.get("station", {}) or {}).get("name", name),
            "category": (manifest.get("station", {}) or {}).get("category", ""),
            "host": (manifest.get("station", {}) or {}).get("host", ""),
            "meta_plugin": manifest.get("meta_plugin", (manifest.get("station", {}) or {}).get("meta_plugin", "radio_station")),
            "logo": (manifest.get("station", {}) or {}).get("logo", ""),
        })
    return stations


# ─── Plugin & meta-plugin discovery ────────────────────────────────────────
import importlib.util
import shutil

def discover_plugins() -> Dict[str, Dict[str, Any]]:
    """Discover feed/widget plugins (mirrors shell_bookmark.discover_plugins)."""
    plugins: Dict[str, Dict[str, Any]] = {}
    if not os.path.exists(PLUGINS_DIR):
        return plugins
    for fn in sorted(os.listdir(PLUGINS_DIR)):
        if not fn.endswith(".py"):
            continue
        name = os.path.splitext(fn)[0]
        path = os.path.join(PLUGINS_DIR, fn)
        info: Dict[str, Any] = {
            "name": name, "display": name, "desc": "",
            "path": path, "is_feed": True, "defaults": None,
        }
        try:
            spec = importlib.util.spec_from_file_location(name, path)
            mod = importlib.util.module_from_spec(spec)
            assert spec and spec.loader
            spec.loader.exec_module(mod)
            info["display"] = getattr(mod, "PLUGIN_NAME", name)
            info["desc"]    = getattr(mod, "PLUGIN_DESC", "")
            info["is_feed"] = bool(getattr(mod, "IS_FEED", True))
            d = (getattr(mod, "FEED_DEFAULTS", None)
                 or getattr(mod, "DEFAULT_FEED_CFG", None)
                 or getattr(mod, "DEFAULT_CONFIG", None))
            if isinstance(d, dict):
                info["defaults"] = d
        except Exception:
            pass
        plugins[name] = info
    return plugins


def discover_meta_plugins() -> List[str]:
    """Discover available meta plugins."""
    if not os.path.exists(META_PLUGINS_DIR):
        return ["radio_station"]
    plugins = []
    for fn in sorted(os.listdir(META_PLUGINS_DIR)):
        if fn.endswith(".py") and not fn.startswith("__"):
            plugins.append(os.path.splitext(fn)[0])
    return plugins if plugins else ["radio_station"]


def discover_voices() -> List[str]:
    """List available voice model files."""
    voices = []
    if os.path.isdir(VOICES_DIR):
        for fn in sorted(os.listdir(VOICES_DIR)):
            if fn.endswith(".onnx"):
                voices.append(fn)
    return voices


def safe_read_yaml(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def safe_write_yaml(path: str, obj: dict):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        yaml.safe_dump(obj, f, sort_keys=False, allow_unicode=True)
    os.replace(tmp, path)


# ═══════════════════════════════════════════════════════════════════════════
# Station Process Manager — headless bookmark.py instances
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class ManagedStation:
    """A running headless station."""
    station_id: str
    proc: subprocess.Popen
    started_at: float = field(default_factory=time.time)
    web_port: Optional[int] = None  # e.g. 7555 for FTB
    audio_ws_clients: Set[Any] = field(default_factory=set)

    def is_alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None


class StationManager:
    """Manages headless bookmark.py station processes."""

    FTB_BASE_PORT = 7555  # Fixed port — only one station runs at a time

    def __init__(self):
        self._stations: Dict[str, ManagedStation] = {}
        self._lock = threading.Lock()

    def list_running(self) -> List[Dict[str, Any]]:
        with self._lock:
            result = []
            for sid, ms in list(self._stations.items()):
                if not ms.is_alive():
                    self._stations.pop(sid, None)
                    continue
                result.append({
                    "station_id": sid,
                    "pid": ms.proc.pid,
                    "uptime_sec": int(time.time() - ms.started_at),
                    "web_port": ms.web_port,
                })
            return result

    def get(self, station_id: str) -> Optional[ManagedStation]:
        with self._lock:
            ms = self._stations.get(station_id)
            if ms and not ms.is_alive():
                self._stations.pop(station_id, None)
                return None
            return ms

    def launch(self, station_id: str) -> Dict[str, Any]:
        """Launch a headless station runtime. Only one station at a time."""
        with self._lock:
            # Already running?
            existing = self._stations.get(station_id)
            if existing and existing.is_alive():
                return {
                    "status": "already_running",
                    "station_id": station_id,
                    "pid": existing.proc.pid,
                    "web_port": existing.web_port,
                }

            # ── Enforce single-station limit ──
            # Stop any other running station before launching a new one
            for sid, ms in list(self._stations.items()):
                if ms.is_alive():
                    self._kill_and_wait(ms)
            self._stations.clear()

            station_path = os.path.join(STATIONS_DIR, station_id)
            manifest_path = os.path.join(station_path, "manifest.yaml")
            if not os.path.exists(manifest_path):
                return {"status": "error", "message": f"Station {station_id} not found"}

            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    cfg = yaml.safe_load(f) or {}
            except Exception as e:
                return {"status": "error", "message": str(e)}

            env = os.environ.copy()
            env["STATION_DIR"] = station_path
            env["STATION_DB_PATH"] = os.path.join(station_path, cfg.get("paths", {}).get("db", "station.sqlite"))
            env["STATION_MEMORY_PATH"] = os.path.join(station_path, cfg.get("paths", {}).get("memory", "station_memory.json"))
            env["RADIO_OS_ROOT"] = BASE_DIR
            env["RADIO_OS_PLUGINS"] = PLUGINS_DIR
            env["RADIO_OS_VOICES"] = os.path.join(BASE_DIR, "voices")

            # Headless mode — no tkinter UI, audio pipes to WebSocket
            env["RADIO_OS_HEADLESS"] = "1"
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONUNBUFFERED"] = "1"

            # Inject global API keys
            global_cfg = get_global_config()
            env_vars = global_cfg.get("environment", {})
            for var_name, var_value in env_vars.items():
                if isinstance(var_value, str) and var_value.strip():
                    env[var_name] = var_value

            default_models = global_cfg.get("default_models", {})
            openai_key = default_models.get("openai_api_key", "").strip()
            if openai_key and "OPENAI_API_KEY" not in env:
                env["OPENAI_API_KEY"] = openai_key

            # Visual model config
            visual_cfg = global_cfg.get("visual_models", {})
            if "visual_models" in cfg:
                visual_cfg.update(cfg["visual_models"])
            if visual_cfg:
                env["VISUAL_MODEL_TYPE"] = str(visual_cfg.get("model_type", "local"))
                env["VISUAL_MODEL_LOCAL"] = str(visual_cfg.get("local_model", ""))
                env["VISUAL_MODEL_API_PROVIDER"] = str(visual_cfg.get("api_provider", ""))
                env["VISUAL_MODEL_API_MODEL"] = str(visual_cfg.get("api_model", ""))
                env["VISUAL_MODEL_API_KEY"] = str(visual_cfg.get("api_key", ""))
                env["VISUAL_MODEL_API_ENDPOINT"] = str(visual_cfg.get("api_endpoint", ""))

            # Assign a web port for the station's own web server (FTB, etc.)
            # Always use the fixed base port — only one station runs at a time
            web_port = self.FTB_BASE_PORT
            env["FTB_WEB_PORT"] = str(web_port)

            # Log output
            log_path = os.path.join(station_path, "runtime.log")
            log_file = None
            try:
                log_file = open(log_path, "a", encoding="utf-8", errors="ignore")
                log_file.write(f"\n\n===== WEB LAUNCH {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n")
                log_file.flush()
            except Exception:
                log_file = None

            cmd = [sys.executable, "-u", RUNTIME_PATH]
            kwargs: Dict[str, Any] = {
                "cwd": BASE_DIR,
                "env": env,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.STDOUT,
                "text": True,
                "encoding": "utf-8",
                "errors": "replace",
            }

            try:
                proc = subprocess.Popen(cmd, **kwargs)
            except Exception as e:
                return {"status": "error", "message": f"Failed to spawn process: {e}"}

            ms = ManagedStation(
                station_id=station_id,
                proc=proc,
                web_port=web_port,
            )
            self._stations[station_id] = ms

            # Log capture thread
            if log_file:
                def _capture(p=proc, lf=log_file):
                    try:
                        while p.poll() is None:
                            line = p.stdout.readline()
                            if line:
                                lf.write(line)
                                lf.flush()
                            else:
                                break
                        remaining = p.stdout.read()
                        if remaining:
                            lf.write(remaining)
                            lf.flush()
                    except Exception:
                        pass
                threading.Thread(target=_capture, daemon=True).start()

            # ── Health check: wait briefly and see if it crashed ──
            time.sleep(1.5)
            if proc.poll() is not None:
                # Process already exited — grab what output we can
                exit_code = proc.returncode
                output = ""
                try:
                    if log_file:
                        log_file.flush()
                        log_file.close()
                    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                        output = f.read()[-2000:]  # last 2KB
                except Exception:
                    pass
                self._stations.pop(station_id, None)
                return {
                    "status": "error",
                    "message": f"Station process exited immediately (code {exit_code})",
                    "exit_code": exit_code,
                    "output": output,
                }

            return {
                "status": "launched",
                "station_id": station_id,
                "pid": proc.pid,
                "web_port": web_port,
            }

    def _kill_and_wait(self, ms: ManagedStation) -> None:
        """Terminate a managed station process, wait for it to die, and
        ensure the web port is released before returning."""
        try:
            ms.proc.terminate()
            ms.proc.wait(timeout=5)
        except Exception:
            try:
                ms.proc.kill()
                ms.proc.wait(timeout=3)
            except Exception:
                pass

        # Wait briefly for the OS to release the port so the next
        # launch can bind to the same port without EADDRINUSE.
        if ms.web_port:
            import socket
            for _ in range(20):          # up to ~2 s
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    if s.connect_ex(("127.0.0.1", ms.web_port)) != 0:
                        break            # port is free
                time.sleep(0.1)

    def stop(self, station_id: str) -> Dict[str, Any]:
        with self._lock:
            ms = self._stations.pop(station_id, None)
            if not ms:
                return {"status": "not_running", "station_id": station_id}
            self._kill_and_wait(ms)
            return {"status": "stopped", "station_id": station_id}

    def stop_all(self):
        with self._lock:
            for sid, ms in list(self._stations.items()):
                self._kill_and_wait(ms)
            self._stations.clear()


# ═══════════════════════════════════════════════════════════════════════════
# Audio Bridge — captures TTS audio from station and streams to WebSocket
# ═══════════════════════════════════════════════════════════════════════════

class AudioBridge:
    """
    Captures audio data from station runtimes and streams to connected
    WebSocket clients. In headless mode, bookmark.py writes WAV files
    to <station_dir>/.audio_pipe/. This bridge is polled by the async
    WebSocket handler — no background threads needed.
    """

    def __init__(self):
        pass

    def reset(self, station_id: str):
        """Clear stale audio files for a station before (re)launch."""
        audio_dir = os.path.join(STATIONS_DIR, station_id, ".audio_pipe")
        if os.path.isdir(audio_dir):
            try:
                for f in os.listdir(audio_dir):
                    fp = os.path.join(audio_dir, f)
                    try:
                        os.remove(fp)
                    except Exception:
                        pass
                print(f"[AudioBridge] Cleared audio pipe for {station_id}", flush=True)
            except Exception:
                pass

    def poll_new_segments(self, station_id: str) -> List[Tuple[bytes, dict]]:
        """
        Check for new WAV segments in the station's audio pipe dir.
        Returns list of (payload_bytes, metadata_dict).
        Each payload is: 4-byte JSON length (big-endian) + JSON metadata + WAV bytes.
        Consumed files are deleted after reading.
        """
        audio_dir = os.path.join(STATIONS_DIR, station_id, ".audio_pipe")
        if not os.path.isdir(audio_dir):
            return []

        results = []

        try:
            files = sorted(f for f in os.listdir(audio_dir)
                           if f.endswith(".wav"))
        except Exception:
            return []

        for fname in files:
            fpath = os.path.join(audio_dir, fname)
            meta_path = fpath + ".json"

            # Skip if the file is still being written (< 200ms old)
            try:
                age = time.time() - os.path.getmtime(fpath)
                if age < 0.2:
                    continue
            except Exception:
                continue

            # Wait for metadata companion file too
            if not os.path.exists(meta_path):
                try:
                    meta_age = time.time() - os.path.getmtime(fpath)
                    if meta_age < 1.0:
                        continue  # JSON may still be arriving
                except Exception:
                    pass

            try:
                with open(fpath, "rb") as wf:
                    wav_bytes = wf.read()
                if len(wav_bytes) < 44:
                    continue  # WAV header alone is 44 bytes, skip empty/corrupt
            except Exception:
                continue

            meta = {}
            if os.path.exists(meta_path):
                try:
                    with open(meta_path, "r") as mf:
                        meta = json.load(mf)
                except Exception:
                    pass

            # Build binary payload: [4-byte meta len][JSON meta][WAV data]
            meta_json = json.dumps(meta).encode("utf-8")
            header = struct.pack(">I", len(meta_json))
            payload = header + meta_json + wav_bytes
            results.append((payload, meta))

            # Clean up consumed files
            try:
                os.remove(fpath)
            except Exception:
                pass
            try:
                if os.path.exists(meta_path):
                    os.remove(meta_path)
            except Exception:
                pass

        return results


# ═══════════════════════════════════════════════════════════════════════════
# FastAPI Application
# ═══════════════════════════════════════════════════════════════════════════

WEB_SHELL_PORT = int(os.environ.get("RADIO_OS_WEB_PORT", "7800"))

def create_shell_app(station_mgr: StationManager, audio_bridge: AudioBridge):
    """Build the Radio OS web shell FastAPI app."""
    _ensure_imports()
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
    from fastapi.responses import JSONResponse, HTMLResponse, FileResponse, RedirectResponse
    from fastapi.staticfiles import StaticFiles
    from fastapi.middleware.cors import CORSMiddleware

    app = FastAPI(title="Radio OS Web Shell", version="1.0.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ──── REST: Health ────
    @app.get("/api/health")
    async def health():
        return {
            "status": "ok",
            "ts": time.time(),
            "version": "1.06",
        }

    # ──── REST: List stations ────
    @app.get("/api/stations")
    async def list_stations():
        stations = discover_stations()
        running = {s["station_id"]: s for s in station_mgr.list_running()}
        for st in stations:
            rt = running.get(st["station_id"])
            st["running"] = rt is not None
            st["pid"] = rt["pid"] if rt else None
            st["web_port"] = rt["web_port"] if rt else None
            st["uptime_sec"] = rt["uptime_sec"] if rt else None
        return {"stations": stations}

    # ──── REST: Launch station ────
    @app.post("/api/stations/{station_id}/launch")
    async def launch_station(station_id: str):
        # Clear stale audio pipe before launching
        audio_bridge.reset(station_id)
        result = station_mgr.launch(station_id)
        code = 200 if result["status"] in ("launched", "already_running") else 400
        return JSONResponse(result, status_code=code)

    # ──── REST: Stop station ────
    @app.post("/api/stations/{station_id}/stop")
    async def stop_station(station_id: str):
        result = station_mgr.stop(station_id)
        # Clear stale audio pipe so next launch starts clean
        audio_bridge.reset(station_id)
        return JSONResponse(result)

    # ──── REST: Station status ────
    @app.get("/api/stations/{station_id}/status")
    async def station_status(station_id: str):
        ms = station_mgr.get(station_id)
        if not ms:
            return JSONResponse({"status": "not_running", "station_id": station_id})

        # Read status.json from station dir
        status_path = os.path.join(STATIONS_DIR, station_id, "status.json")
        status_data = {}
        if os.path.exists(status_path):
            try:
                with open(status_path, "r", encoding="utf-8") as f:
                    status_data = json.load(f)
            except Exception:
                pass

        return {
            "status": "running",
            "station_id": station_id,
            "pid": ms.proc.pid,
            "uptime_sec": int(time.time() - ms.started_at),
            "web_port": ms.web_port,
            "runtime_status": status_data,
        }

    # ──── REST: Station runtime log tail ────
    @app.get("/api/stations/{station_id}/log")
    async def station_log(station_id: str, lines: int = 50):
        log_path = os.path.join(STATIONS_DIR, station_id, "runtime.log")
        if not os.path.exists(log_path):
            return {"log": "", "lines": 0}
        try:
            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            tail = content.strip().splitlines()[-lines:]
            return {"log": "\n".join(tail), "lines": len(tail)}
        except Exception as e:
            return JSONResponse({"error": str(e)}, 500)

    # ──── REST: Global settings ────
    @app.get("/api/settings")
    async def get_settings():
        return get_global_config()

    @app.post("/api/settings")
    async def update_settings(payload: Dict[str, Any]):
        cfg = get_global_config()
        cfg.update(payload)
        save_global_config(cfg)
        return {"status": "saved"}

    # ──── REST: Settings sections (granular save like shell_bookmark) ────
    @app.get("/api/settings/general")
    async def get_general_settings():
        cfg = get_global_config()
        return cfg.get("general", {})

    @app.post("/api/settings/general")
    async def save_general_settings(request: Request):
        payload = await request.json()
        cfg = get_global_config()
        cfg["general"] = payload
        save_global_config(cfg)
        return {"status": "saved"}

    @app.get("/api/settings/models")
    async def get_model_settings():
        cfg = get_global_config()
        return cfg.get("default_models", {})

    @app.post("/api/settings/models")
    async def save_model_settings(request: Request):
        payload = await request.json()
        cfg = get_global_config()
        cfg["default_models"] = payload
        save_global_config(cfg)
        return {"status": "saved"}

    @app.get("/api/settings/voices")
    async def get_voice_settings():
        cfg = get_global_config()
        return cfg.get("default_voices", {})

    @app.post("/api/settings/voices")
    async def save_voice_settings(request: Request):
        payload = await request.json()
        cfg = get_global_config()
        cfg["default_voices"] = payload
        save_global_config(cfg)
        return {"status": "saved"}

    @app.get("/api/settings/environment")
    async def get_environment_settings():
        cfg = get_global_config()
        return cfg.get("environment", {})

    @app.post("/api/settings/environment")
    async def save_environment_settings(request: Request):
        payload = await request.json()
        cfg = get_global_config()
        cfg["environment"] = payload
        save_global_config(cfg)
        return {"status": "saved"}

    @app.get("/api/settings/visual_models")
    async def get_visual_model_settings():
        cfg = get_global_config()
        return cfg.get("visual_models", {})

    @app.post("/api/settings/visual_models")
    async def save_visual_model_settings(request: Request):
        payload = await request.json()
        cfg = get_global_config()
        cfg["visual_models"] = payload
        save_global_config(cfg)
        return {"status": "saved"}

    # ──── REST: Plugins ────
    @app.get("/api/plugins")
    async def list_plugins():
        return {"plugins": discover_plugins()}

    @app.get("/api/meta_plugins")
    async def list_meta_plugins():
        return {"meta_plugins": discover_meta_plugins()}

    @app.get("/api/voices")
    async def list_voices():
        return {"voices": discover_voices()}

    # ──── REST: Station CRUD ────
    @app.get("/api/stations/{station_id}/manifest")
    async def get_station_manifest(station_id: str):
        mp = os.path.join(STATIONS_DIR, station_id, "manifest.yaml")
        if not os.path.exists(mp):
            return JSONResponse({"error": "Station not found"}, 404)
        return safe_read_yaml(mp)

    @app.put("/api/stations/{station_id}/manifest")
    async def save_station_manifest(station_id: str, request: Request):
        payload = await request.json()
        station_dir = os.path.join(STATIONS_DIR, station_id)
        os.makedirs(station_dir, exist_ok=True)
        mp = os.path.join(station_dir, "manifest.yaml")
        safe_write_yaml(mp, payload)
        return {"status": "saved", "station_id": station_id}

    @app.post("/api/stations/create")
    async def create_station(request: Request):
        """Create a new station from manifest data."""
        payload = await request.json()
        station_id = payload.get("station_id", "").strip()
        manifest = payload.get("manifest", {})
        if not station_id:
            return JSONResponse({"error": "station_id is required"}, 400)
        # Sanitize
        bad = any(c in station_id for c in r'\/:*?"<>| ')
        if bad:
            return JSONResponse({"error": "station_id contains invalid characters"}, 400)
        station_dir = os.path.join(STATIONS_DIR, station_id)
        if os.path.exists(station_dir):
            return JSONResponse({"error": f"Station '{station_id}' already exists"}, 409)
        os.makedirs(station_dir, exist_ok=True)
        # Ensure station.id in manifest
        manifest.setdefault("station", {})["id"] = station_id
        mp = os.path.join(station_dir, "manifest.yaml")
        safe_write_yaml(mp, manifest)
        return {"status": "created", "station_id": station_id}

    @app.delete("/api/stations/{station_id}")
    async def delete_station(station_id: str):
        """Delete a station (stops it first if running)."""
        station_dir = os.path.join(STATIONS_DIR, station_id)
        if not os.path.isdir(station_dir):
            return JSONResponse({"error": "Station not found"}, 404)
        # Stop if running
        station_mgr.stop(station_id)
        try:
            shutil.rmtree(station_dir)
        except Exception as e:
            return JSONResponse({"error": f"Delete failed: {e}"}, 500)
        return {"status": "deleted", "station_id": station_id}

    # ──── REST: Storage tools ────
    @app.post("/api/storage/clear_logs")
    async def clear_all_logs():
        count = 0
        for name in os.listdir(STATIONS_DIR):
            lp = os.path.join(STATIONS_DIR, name, "runtime.log")
            if os.path.exists(lp):
                try:
                    os.remove(lp)
                    count += 1
                except Exception:
                    pass
        return {"status": "cleared", "count": count}

    @app.post("/api/storage/vacuum_databases")
    async def vacuum_databases():
        import sqlite3
        count = 0
        for name in os.listdir(STATIONS_DIR):
            db = os.path.join(STATIONS_DIR, name, "station.sqlite")
            if os.path.exists(db):
                try:
                    conn = sqlite3.connect(db)
                    conn.execute("VACUUM")
                    conn.close()
                    count += 1
                except Exception:
                    pass
        return {"status": "vacuumed", "count": count}

    @app.get("/api/storage/info")
    async def storage_info():
        """Return config paths and station disk usage."""
        cfg_path = get_global_config_path()
        station_sizes = {}
        for name in os.listdir(STATIONS_DIR) if os.path.isdir(STATIONS_DIR) else []:
            sp = os.path.join(STATIONS_DIR, name)
            if not os.path.isdir(sp):
                continue
            total = 0
            for root, dirs, files in os.walk(sp):
                for f in files:
                    try:
                        total += os.path.getsize(os.path.join(root, f))
                    except Exception:
                        pass
            station_sizes[name] = total
        return {
            "config_path": cfg_path,
            "stations_dir": STATIONS_DIR,
            "station_sizes": station_sizes,
        }

    # ──── REST: Station logo ────
    @app.get("/api/stations/{station_id}/logo")
    async def station_logo(station_id: str):
        station_path = os.path.join(STATIONS_DIR, station_id)
        mp = os.path.join(station_path, "manifest.yaml")
        if os.path.exists(mp):
            try:
                with open(mp, "r", encoding="utf-8") as f:
                    manifest = yaml.safe_load(f) or {}
                logo = (manifest.get("station", {}) or {}).get("logo", "")
                if logo:
                    logo_path = os.path.join(station_path, logo)
                    if os.path.exists(logo_path):
                        return FileResponse(logo_path)
                    # Try relative to BASE_DIR
                    logo_path = os.path.join(BASE_DIR, logo)
                    if os.path.exists(logo_path):
                        return FileResponse(logo_path)
            except Exception:
                pass
        # Default icon
        default_icon = os.path.join(BASE_DIR, "radioos.png")
        if os.path.exists(default_icon):
            return FileResponse(default_icon)
        return JSONResponse({"error": "no logo"}, 404)

    # ──── Station Runtime Dashboard (the main station Web UI) ────
    @app.get("/runtime/{station_id}")
    async def station_runtime_dashboard(station_id: str):
        """
        Full-page station runtime dashboard — the web equivalent of
        bookmark.py's tkinter StationUI. Shows live log, audio player
        with subtitles, station controls, and links to plugin web UIs.
        """
        # Load manifest for display info
        mp = os.path.join(STATIONS_DIR, station_id, "manifest.yaml")
        station_name = station_id
        station_category = ""
        station_host = ""
        if os.path.exists(mp):
            try:
                with open(mp, "r", encoding="utf-8") as f:
                    manifest = yaml.safe_load(f) or {}
                station_name = (manifest.get("station", {}) or {}).get("name", station_id)
                station_category = (manifest.get("station", {}) or {}).get("category", "")
                station_host = (manifest.get("characters", {}) or {}).get("host", {}).get("name", "")
            except Exception:
                pass

        return HTMLResponse(_RUNTIME_DASHBOARD_HTML
            .replace("{{STATION_ID}}", station_id)
            .replace("{{STATION_NAME}}", station_name)
            .replace("{{STATION_CATEGORY}}", station_category)
            .replace("{{STATION_HOST}}", station_host)
        )

    # ──── Proxy to station plugin web servers (e.g. FTB on :7555) ────
    @app.api_route("/station/{station_id}/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
    async def proxy_station_web(station_id: str, path: str, request: Request):
        """
        Proxy requests to a station's embedded plugin web server.
        e.g. /station/BasketballFM/ → http://localhost:7555/
        Passes through raw response with correct content-type (HTML, CSS, JS, etc.)
        """
        ms = station_mgr.get(station_id)
        if not ms or not ms.web_port:
            return JSONResponse({"error": "Station not running or no web port"}, 503)

        try:
            import httpx
        except ImportError:
            return JSONResponse({"error": "httpx not installed — run: pip install httpx"}, 501)

        target_url = f"http://127.0.0.1:{ms.web_port}/{path}"
        query = str(request.url.query)
        if query:
            target_url += f"?{query}"

        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.request(
                    method=request.method,
                    url=target_url,
                    headers={k: v for k, v in request.headers.items()
                             if k.lower() not in ("host", "connection")},
                    content=await request.body(),
                )
                from starlette.responses import Response
                # Pass through the raw bytes with correct content-type
                content_type = resp.headers.get("content-type", "application/octet-stream")
                return Response(
                    content=resp.content,
                    status_code=resp.status_code,
                    media_type=content_type,
                )
        except Exception as e:
            return JSONResponse({"error": f"Proxy failed: {e}"}, 502)

    # ──── WebSocket: Audio stream from station ────
    @app.websocket("/ws/audio/{station_id}")
    async def ws_audio(ws: WebSocket, station_id: str):
        await ws.accept()
        print(f"[AudioWS] Client connected for station '{station_id}'", flush=True)
        sent_count = 0

        # Run reader and poller concurrently
        stop = asyncio.Event()

        async def reader():
            """Read client messages (keepalive pings). Exits on disconnect."""
            try:
                while not stop.is_set():
                    msg = await ws.receive()
                    if msg["type"] == "websocket.disconnect":
                        stop.set()
                        return
                    text = msg.get("text", "")
                    if text == "ping":
                        try:
                            await ws.send_text("pong")
                        except Exception:
                            stop.set()
                            return
            except Exception:
                stop.set()

        async def poller():
            """Poll audio pipe and send segments to client."""
            nonlocal sent_count
            try:
                while not stop.is_set():
                    segments = audio_bridge.poll_new_segments(station_id)
                    if segments:
                        print(f"[AudioWS] {station_id}: found {len(segments)} segment(s)", flush=True)
                    for payload, meta in segments:
                        try:
                            await ws.send_bytes(payload)
                            sent_count += 1
                            voice = meta.get("voice", "?")
                            text_preview = meta.get("text", "")[:50]
                            print(f"[AudioWS] {station_id}: sent #{sent_count} ({len(payload)}B) {voice}: {text_preview}", flush=True)
                        except Exception as e:
                            print(f"[AudioWS] {station_id}: send failed: {e}", flush=True)
                            stop.set()
                            return
                    await asyncio.sleep(0.5)
            except Exception as e:
                print(f"[AudioWS] {station_id}: poller error: {e}", flush=True)
                stop.set()

        try:
            await asyncio.gather(reader(), poller())
        except Exception:
            pass

        print(f"[AudioWS] {station_id}: disconnected (sent {sent_count} segments)", flush=True)

    # ──── WebSocket: Station event stream (proxy to station WS) ────
    @app.websocket("/ws/station/{station_id}")
    async def ws_station(ws: WebSocket, station_id: str):
        """Proxy WebSocket to station's /ws/live endpoint."""
        ms = station_mgr.get(station_id)
        if not ms or not ms.web_port:
            await ws.close(code=1008, reason="Station not running")
            return

        await ws.accept()

        try:
            import websockets
        except ImportError:
            await ws.send_text(json.dumps({"type": "error", "data": "websockets not installed — run: pip install websockets"}))
            await ws.close()
            return

        station_ws_url = f"ws://127.0.0.1:{ms.web_port}/ws/live"

        try:
            async with websockets.connect(station_ws_url) as station_ws:
                # Bidirectional proxy
                async def client_to_station():
                    try:
                        async for msg in ws.iter_text():
                            await station_ws.send(msg)
                    except Exception:
                        pass

                async def station_to_client():
                    try:
                        async for msg in station_ws:
                            await ws.send_text(msg)
                    except Exception:
                        pass

                await asyncio.gather(
                    client_to_station(),
                    station_to_client(),
                )
        except Exception as e:
            try:
                await ws.send_text(json.dumps({"type": "error", "data": f"WS proxy failed: {e}"}))
            except Exception:
                pass
        finally:
            try:
                await ws.close()
            except Exception:
                pass

    # ──── Serve the web shell frontend ────
    shell_dist = os.path.join(BASE_DIR, "web_shell", "dist")
    shell_static = os.path.join(BASE_DIR, "web_shell")

    @app.get("/")
    async def serve_shell():
        # Try built SPA first
        index = os.path.join(shell_dist, "index.html")
        if os.path.exists(index):
            with open(index, "r", encoding="utf-8") as f:
                return HTMLResponse(f.read())

        # Fall back to self-contained HTML
        return HTMLResponse(_EMBEDDED_SHELL_HTML)

    # Mount static assets if they exist
    if os.path.isdir(os.path.join(shell_dist, "assets")):
        app.mount("/assets", StaticFiles(directory=os.path.join(shell_dist, "assets")), name="shell_assets")

    return app


# ═══════════════════════════════════════════════════════════════════════════
# Embedded HTML — full management SPA (no build step needed)
# ═══════════════════════════════════════════════════════════════════════════

_EMBEDDED_SHELL_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Radio OS</title>
<style>
:root{--bg:#0e0e0e;--panel:#121212;--card:#181818;--card-hover:#222;--surface:#0a0a0a;--text:#e8e8e8;--muted:#9a9a9a;--accent:#4cc9f0;--danger:#ff4d6d;--good:#2ee59d;--warn:#f0c040}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:var(--bg);color:var(--text);min-height:100vh;display:flex}
input,select,textarea{font-family:inherit;font-size:13px;background:var(--surface);color:var(--text);border:1px solid #333;border-radius:6px;padding:7px 10px;outline:none;transition:border .15s}
input:focus,select:focus,textarea:focus{border-color:var(--accent)}
textarea{resize:vertical;min-height:60px}
label{font-size:13px;color:var(--muted);display:block;margin-bottom:3px}
.sidebar{width:220px;background:var(--panel);border-right:1px solid #222;display:flex;flex-direction:column;flex-shrink:0;height:100vh;position:sticky;top:0}
.sidebar .logo{padding:16px;display:flex;align-items:center;gap:10px;border-bottom:1px solid #222}
.sidebar .logo h1{font-size:17px;font-weight:700}
.sidebar nav{flex:1;padding:8px 0;overflow-y:auto}
.sidebar nav a{display:flex;align-items:center;gap:10px;padding:10px 16px;color:var(--muted);text-decoration:none;font-size:14px;transition:all .15s;cursor:pointer;border-left:3px solid transparent}
.sidebar nav a:hover{color:var(--text);background:rgba(255,255,255,.03)}
.sidebar nav a.active{color:var(--accent);background:rgba(76,201,240,.06);border-left-color:var(--accent)}
.sidebar nav .section{font-size:11px;color:#555;text-transform:uppercase;padding:16px 16px 4px;letter-spacing:.5px}
.sidebar .server-info{padding:12px 16px;border-top:1px solid #222;font-size:11px;color:var(--muted)}
.main{flex:1;overflow-y:auto;height:100vh}
.page{display:none;padding:24px 32px;max-width:1100px}
.page.active{display:block}
.page h2{font-size:22px;font-weight:700;margin-bottom:4px}
.page .subtitle{font-size:13px;color:var(--muted);margin-bottom:20px}
.station-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:16px}
.station-card{background:var(--card);border-radius:12px;padding:20px;border:1px solid transparent;transition:all .2s;position:relative;cursor:pointer}
.station-card:hover{background:var(--card-hover);border-color:var(--accent)}
.station-card.running{border-color:var(--good)}
.station-card .name{font-size:17px;font-weight:600;margin-bottom:3px}
.station-card .cat{font-size:12px;color:var(--muted);margin-bottom:10px}
.station-card .meta{font-size:11px;color:var(--muted)}
.station-card .badge{position:absolute;top:12px;right:12px;font-size:10px;padding:3px 8px;border-radius:6px;font-weight:700}
.station-card .badge.live{background:var(--good);color:#000}
.station-card .badge.idle{background:#333;color:var(--muted)}
.station-card .actions{display:flex;gap:6px;margin-top:12px}
.btn{padding:7px 14px;border:none;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;transition:all .12s;display:inline-flex;align-items:center;gap:5px}
.btn-primary{background:var(--accent);color:#000}.btn-primary:hover{filter:brightness(1.1)}
.btn-danger{background:var(--danger);color:#fff}.btn-danger:hover{filter:brightness(1.1)}
.btn-secondary{background:#333;color:var(--text)}.btn-secondary:hover{background:#444}
.btn-good{background:var(--good);color:#000}
.btn-sm{padding:5px 10px;font-size:11px}
.btn:disabled{opacity:.35;cursor:not-allowed}
.form-group{margin-bottom:14px}
.form-group label{margin-bottom:4px}
.form-row{display:flex;gap:14px;flex-wrap:wrap}
.form-row .form-group{flex:1;min-width:200px}
.card-section{background:var(--card);border-radius:10px;padding:16px 20px;margin-bottom:16px}
.card-section h3{font-size:15px;font-weight:600;margin-bottom:10px;display:flex;align-items:center;gap:8px}
.toggle{display:flex;align-items:center;gap:8px;font-size:13px;cursor:pointer}
.toggle input[type=checkbox]{width:16px;height:16px;accent-color:var(--accent)}
.tag{display:inline-block;padding:2px 8px;border-radius:4px;background:#333;color:var(--muted);font-size:11px;margin:2px}
.log-box{background:var(--surface);padding:12px;border-radius:8px;font-family:'SF Mono','Fira Code',monospace;font-size:11px;max-height:500px;overflow-y:auto;white-space:pre-wrap;color:var(--muted);line-height:1.6}
.tab-bar{display:flex;gap:0;border-bottom:1px solid #333;margin-bottom:16px}
.tab-bar button{padding:10px 18px;border:none;background:none;color:var(--muted);font-size:13px;font-weight:500;cursor:pointer;border-bottom:2px solid transparent;transition:all .15s}
.tab-bar button:hover{color:var(--text)}
.tab-bar button.active{color:var(--accent);border-bottom-color:var(--accent)}
.tab-pane{display:none}.tab-pane.active{display:block}
.audio-bar{position:fixed;bottom:0;left:220px;right:0;background:#000;padding:10px 24px;display:none;align-items:center;gap:16px;border-top:1px solid #222;z-index:100}
.audio-bar.active{display:flex}
.audio-bar .now{font-size:14px;font-weight:600;flex:1}.audio-bar .sub{font-size:12px;color:var(--muted);flex:2}
.toast{position:fixed;bottom:20px;right:20px;background:var(--card);padding:10px 18px;border-radius:8px;border:1px solid var(--accent);font-size:12px;z-index:999;animation:fadeUp .2s}
@keyframes fadeUp{from{opacity:0;transform:translateY(8px)}to{opacity:1}}
.modal-backdrop{position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:200;display:flex;align-items:center;justify-content:center}
.modal{background:var(--panel);border-radius:14px;padding:24px;min-width:500px;max-width:800px;max-height:85vh;overflow-y:auto;border:1px solid #333}
.modal h3{font-size:18px;margin-bottom:16px}
@media(max-width:768px){.sidebar{width:60px}.sidebar .logo h1,.sidebar nav a span,.sidebar nav .section,.sidebar .server-info{display:none}.sidebar nav a{justify-content:center;padding:12px}.main{padding:0}.page{padding:16px}}
</style>
</head>
<body>

<div class="sidebar">
  <div class="logo"><span style="font-size:24px">📻</span><h1>Radio OS</h1></div>
  <nav>
    <div class="section">Stations</div>
    <a onclick="showPage('home')" data-page="home" class="active"><span>🏠</span><span>Home</span></a>
    <a onclick="showPage('new_station')" data-page="new_station"><span>➕</span><span>New Station</span></a>
    <div class="section">Settings</div>
    <a onclick="showPage('settings_general')" data-page="settings_general"><span>⚙️</span><span>General</span></a>
    <a onclick="showPage('settings_models')" data-page="settings_models"><span>🧠</span><span>Models</span></a>
    <a onclick="showPage('settings_voices')" data-page="settings_voices"><span>🎙️</span><span>Voices</span></a>
    <a onclick="showPage('settings_env')" data-page="settings_env"><span>🔑</span><span>Environment</span></a>
    <a onclick="showPage('settings_visual')" data-page="settings_visual"><span>👁️</span><span>Vision</span></a>
    <a onclick="showPage('storage')" data-page="storage"><span>💾</span><span>Storage</span></a>
    <a onclick="showPage('plugins')" data-page="plugins"><span>🧩</span><span>Plugins</span></a>
  </nav>
  <div class="server-info" id="serverInfo">Connecting...</div>
</div>

<div class="main">

<!-- ═══════ HOME ═══════ -->
<div class="page active" id="page_home">
  <h2>Stations</h2>
  <p class="subtitle">Launch, monitor, and manage your radio stations</p>
  <div class="station-grid" id="stationGrid"><p style="color:var(--muted)">Loading...</p></div>
  <div id="runtimePanel" style="margin-top:20px;display:none">
    <div class="card-section">
      <h3 id="runtimeTitle">Runtime</h3>
      <div style="display:flex;gap:6px;margin-bottom:10px">
        <button class="btn btn-secondary btn-sm" onclick="refreshLog()">↻ Log</button>
        <button class="btn btn-danger btn-sm" onclick="stopActive()">⏹ Stop</button>
        <button class="btn btn-secondary btn-sm" onclick="openStationUI()">🌐 Web UI</button>
        <button class="btn btn-secondary btn-sm" onclick="editStation(activeStation)">✏️ Edit</button>
      </div>
      <div class="log-box" id="runtimeLog">No logs.</div>
    </div>
  </div>
</div>

<!-- ═══════ NEW / EDIT STATION ═══════ -->
<div class="page" id="page_new_station">
  <h2 id="wizardTitle">New Station</h2>
  <p class="subtitle" id="wizardSubtitle">Create a new radio station</p>
  <div class="tab-bar" id="wizardTabs">
    <button class="active" onclick="wizTab(0)">Basics</button>
    <button onclick="wizTab(1)">Feeds</button>
    <button onclick="wizTab(2)">Characters</button>
    <button onclick="wizTab(3)">Voices</button>
    <button onclick="wizTab(4)">Mix</button>
    <button onclick="wizTab(5)">Review</button>
  </div>
  <!-- Tab 0: Basics -->
  <div class="tab-pane active" id="wiz_0">
    <div class="card-section"><h3>🎚️ Station Identity</h3>
      <div class="form-row">
        <div class="form-group"><label>Station ID (folder name)</label><input id="wz_id" placeholder="my_station"></div>
        <div class="form-group"><label>Station Name</label><input id="wz_name" placeholder="My Radio Station"></div>
      </div>
      <div class="form-row">
        <div class="form-group"><label>Category</label><input id="wz_category" placeholder="Custom"></div>
        <div class="form-group"><label>Host Name</label><input id="wz_host" placeholder="Kai"></div>
      </div>
      <div class="form-row">
        <div class="form-group"><label>Logo (relative path)</label><input id="wz_logo" placeholder="logo.png"></div>
        <div class="form-group"><label>Meta Plugin</label><select id="wz_meta_plugin"></select></div>
      </div>
    </div>
    <div class="card-section"><h3>🧠 Models</h3>
      <div class="form-row">
        <div class="form-group"><label>LLM Provider</label>
          <select id="wz_llm_provider"><option>ollama</option><option>anthropic</option><option>openai</option><option>google</option></select>
        </div>
        <div class="form-group"><label>LLM Endpoint</label><input id="wz_llm_endpoint" placeholder="http://127.0.0.1:11434/api/generate"></div>
      </div>
      <div class="form-row">
        <div class="form-group"><label>Producer Model</label><input id="wz_model_producer" placeholder="gpt-4o"></div>
        <div class="form-group"><label>Host Model</label><input id="wz_model_host" placeholder="gpt-4o"></div>
      </div>
      <div class="form-row">
        <div class="form-group"><label>Navigator Model</label><input id="wz_model_nav" placeholder=""></div>
        <div class="form-group"><label>Embedding Model</label><input id="wz_model_embedding" placeholder=""></div>
      </div>
      <div class="toggle"><input type="checkbox" id="wz_embedding_enabled"><span>Enable Embedding</span></div>
    </div>
  </div>
  <!-- Tab 1: Feeds -->
  <div class="tab-pane" id="wiz_1">
    <div class="card-section"><h3>📡 Feed Plugins</h3>
      <p style="font-size:12px;color:var(--muted);margin-bottom:12px">Enable feeds and configure their settings. Feeds are discovered from installed plugins.</p>
      <div id="feedsList"></div>
    </div>
  </div>
  <!-- Tab 2: Characters -->
  <div class="tab-pane" id="wiz_2">
    <div class="card-section"><h3>👥 Characters</h3>
      <p style="font-size:12px;color:var(--muted);margin-bottom:12px">Define on-air personalities. At least one required.</p>
      <div id="charsList"></div>
      <button class="btn btn-secondary btn-sm" onclick="addCharacter()" style="margin-top:10px">+ Add Character</button>
    </div>
  </div>
  <!-- Tab 3: Voices -->
  <div class="tab-pane" id="wiz_3">
    <div class="card-section"><h3>🎙️ Voice Configuration</h3>
      <div class="form-row">
        <div class="form-group"><label>Voice Provider</label>
          <select id="wz_voices_provider"><option>kokoro</option><option>piper</option><option>openai</option><option>google</option><option>elevenlabs</option></select>
        </div>
        <div class="form-group"><label>Piper Binary Path</label><input id="wz_piper_bin" placeholder="/path/to/piper"></div>
      </div>
      <div id="voiceAssignments"></div>
    </div>
  </div>
  <!-- Tab 4: Mix -->
  <div class="tab-pane" id="wiz_4">
    <div class="card-section"><h3>⚖️ Feed Mix Weights</h3>
      <p style="font-size:12px;color:var(--muted);margin-bottom:12px">How much airtime each feed gets (0-1). Will be normalized.</p>
      <div id="mixWeights"></div>
    </div>
    <div class="card-section"><h3>📊 Scheduler Quotas</h3>
      <p style="font-size:12px;color:var(--muted);margin-bottom:12px">Max items per scheduling round for each feed.</p>
      <div id="schedQuotas"></div>
    </div>
  </div>
  <!-- Tab 5: Review -->
  <div class="tab-pane" id="wiz_5">
    <div class="card-section"><h3>📝 Manifest Preview</h3>
      <button class="btn btn-secondary btn-sm" onclick="refreshWizPreview()" style="margin-bottom:10px">↻ Refresh</button>
      <div class="log-box" id="wizPreview" style="max-height:600px">Click Refresh to preview manifest.</div>
    </div>
  </div>
  <div style="display:flex;gap:8px;margin-top:16px;padding-top:16px;border-top:1px solid #333">
    <button class="btn btn-secondary" onclick="wizPrev()">← Back</button>
    <button class="btn btn-primary" onclick="wizNext()">Next →</button>
    <div style="flex:1"></div>
    <button class="btn btn-secondary" onclick="wizSave()">💾 Save Only</button>
    <button class="btn btn-good" onclick="wizFinish()" id="wizFinishBtn">✅ Create Station</button>
  </div>
</div>

<!-- ═══════ SETTINGS: GENERAL ═══════ -->
<div class="page" id="page_settings_general">
  <h2>General Settings</h2><p class="subtitle">Global preferences</p>
  <div class="card-section">
    <div class="toggle" style="margin-bottom:10px"><input type="checkbox" id="set_auto_start"><span>Auto-start last station on launch</span></div>
    <div class="toggle" style="margin-bottom:10px"><input type="checkbox" id="set_always_server"><span>Always launch web server on startup</span></div>
    <div class="form-row">
      <div class="form-group"><label>Web Server Port</label><input id="set_web_port" type="number" value="7800" style="width:120px"></div>
      <div class="form-group"><label>Status Poll (ms)</label><input id="set_poll_ms" type="number" value="1000" style="width:120px"></div>
    </div>
    <div class="form-row">
      <div class="form-group"><label>Theme</label><select id="set_theme"><option>dark</option><option>midnight</option></select></div>
      <div class="form-group"><label>UI Scale</label><input id="set_scale" type="number" step="0.1" value="1.0" style="width:100px"></div>
    </div>
    <button class="btn btn-primary" onclick="saveGeneral()" style="margin-top:12px">Save Settings</button>
  </div>
</div>

<!-- ═══════ SETTINGS: MODELS ═══════ -->
<div class="page" id="page_settings_models">
  <h2>Default Model Settings</h2><p class="subtitle">Default LLM provider and models for new stations</p>
  <div class="card-section">
    <div class="form-row">
      <div class="form-group"><label>Primary Provider</label>
        <select id="mdl_provider"><option>ollama</option><option>anthropic</option><option>openai</option><option>google</option></select></div>
      <div class="form-group"><label>Ollama/API Endpoint</label><input id="mdl_endpoint" placeholder="http://127.0.0.1:11434/api/generate"></div>
    </div>
    <div class="form-row">
      <div class="form-group"><label>Producer Model</label><input id="mdl_producer" placeholder="gpt-4o"></div>
      <div class="form-group"><label>Host Model</label><input id="mdl_host" placeholder="gpt-4o"></div>
    </div>
    <div class="form-group"><label>Anthropic API Key</label><input id="mdl_anthropic_key" type="password"></div>
    <div class="form-group"><label>OpenAI API Key</label><input id="mdl_openai_key" type="password"></div>
    <div class="form-group"><label>Google API Key</label><input id="mdl_google_key" type="password"></div>
    <button class="btn btn-primary" onclick="saveModels()" style="margin-top:12px">Save Settings</button>
  </div>
</div>

<!-- ═══════ SETTINGS: VOICES ═══════ -->
<div class="page" id="page_settings_voices">
  <h2>Default Voice Settings</h2><p class="subtitle">Global voice paths for new stations</p>
  <div class="card-section">
    <div class="form-row">
      <div class="form-group"><label>Provider</label>
        <select id="vc_provider"><option>kokoro</option><option>piper</option><option>openai</option><option>google</option><option>elevenlabs</option></select></div>
      <div class="form-group"><label>Piper Binary</label><input id="vc_piper_bin" placeholder="/path/to/piper"></div>
    </div>
    <div class="form-group"><label>API Key (for cloud providers)</label><input id="vc_api_key" type="password"></div>
    <div class="form-group"><label>Voices Directory</label><input id="vc_voices_dir" placeholder="voices/"></div>
    <h4 style="margin:12px 0 8px;font-size:13px">Default Character Voices</h4>
    <div class="form-row">
      <div class="form-group"><label>Host</label><input id="vc_host"></div>
      <div class="form-group"><label>Expert</label><input id="vc_expert"></div>
    </div>
    <div class="form-row">
      <div class="form-group"><label>Skeptic</label><input id="vc_skeptic"></div>
      <div class="form-group"><label>Optimist</label><input id="vc_optimist"></div>
    </div>
    <div class="form-group"><label>Coach</label><input id="vc_coach"></div>
    <button class="btn btn-primary" onclick="saveVoices()" style="margin-top:12px">Save Settings</button>
  </div>
</div>

<!-- ═══════ SETTINGS: ENVIRONMENT ═══════ -->
<div class="page" id="page_settings_env">
  <h2>Environment Variables</h2><p class="subtitle">Custom env vars injected into station runtimes</p>
  <div class="card-section">
    <div id="envVarsList"></div>
    <button class="btn btn-secondary btn-sm" onclick="addEnvVar()" style="margin-top:10px">+ Add Variable</button>
    <div style="margin-top:14px;display:flex;gap:8px">
      <button class="btn btn-primary" onclick="saveEnvironment()">Save Environment</button>
      <button class="btn btn-danger" onclick="resetEnvironment()">Reset All</button>
    </div>
  </div>
</div>

<!-- ═══════ SETTINGS: VISUAL MODELS ═══════ -->
<div class="page" id="page_settings_visual">
  <h2>Vision Model Settings</h2><p class="subtitle">Configure visual content analysis models</p>
  <div class="card-section">
    <div class="form-row">
      <div class="form-group"><label>Model Type</label><select id="vis_type"><option>local</option><option>api</option></select></div>
      <div class="form-group"><label>Local Model</label><input id="vis_local" placeholder="llava:7b"></div>
    </div>
    <div class="form-row">
      <div class="form-group"><label>API Provider</label><select id="vis_api_prov"><option></option><option>openai</option><option>anthropic</option><option>google</option></select></div>
      <div class="form-group"><label>API Model</label><input id="vis_api_model" placeholder="gpt-4o"></div>
    </div>
    <div class="form-row">
      <div class="form-group"><label>API Key</label><input id="vis_api_key" type="password"></div>
      <div class="form-group"><label>API Endpoint</label><input id="vis_api_endpoint"></div>
    </div>
    <div class="form-row">
      <div class="form-group"><label>Max Image Size</label><input id="vis_max_size" type="number" value="1024" style="width:100px"></div>
      <div class="form-group"><label>Image Quality</label><select id="vis_quality"><option>low</option><option>high</option><option>auto</option></select></div>
    </div>
    <button class="btn btn-primary" onclick="saveVisual()" style="margin-top:12px">Save Settings</button>
  </div>
</div>

<!-- ═══════ STORAGE ═══════ -->
<div class="page" id="page_storage">
  <h2>Storage & Maintenance</h2><p class="subtitle">Manage logs, databases, and backups</p>
  <div class="card-section"><h3>📋 Log Management</h3>
    <p style="font-size:12px;color:var(--muted);margin-bottom:10px">Clean up old runtime logs</p>
    <button class="btn btn-secondary" onclick="clearAllLogs()">Clear All Station Logs</button>
  </div>
  <div class="card-section"><h3>🗄️ Database Management</h3>
    <p style="font-size:12px;color:var(--muted);margin-bottom:10px">Optimize station databases</p>
    <button class="btn btn-secondary" onclick="vacuumDatabases()">Vacuum All Databases</button>
  </div>
  <div class="card-section"><h3>📊 Disk Usage</h3>
    <div id="diskUsage"><p style="color:var(--muted)">Loading...</p></div>
  </div>
  <div class="card-section"><h3>📁 Configuration</h3>
    <div id="configPaths" style="font-size:12px;color:var(--muted)"></div>
  </div>
</div>

<!-- ═══════ PLUGINS ═══════ -->
<div class="page" id="page_plugins">
  <h2>Installed Plugins</h2><p class="subtitle">Feed and widget plugins discovered in plugins/</p>
  <div id="pluginsList"></div>
</div>

</div><!-- /main -->

<div class="audio-bar" id="audioBar">
  <div class="now" id="nowPlaying">—</div>
  <div class="sub" id="subtitle"></div>
</div>

<script>
// ═══ State ═══
const API='';
let stations=[], activeStation=null, logInterval=null;
let wizPlugins={}, wizMeta=[], wizVoices=[], wizEditMode=false, wizEditId='';
let wizChars={host:{role:'moderator',traits:['calm','smart'],focus:['flow','continuity']}};
let wizFeeds={}, wizMixWeights={}, wizSchedulerQuotas={};
let currentWizTab=0;

// ═══ Navigation ═══
function showPage(id){
  document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.sidebar nav a').forEach(a=>a.classList.remove('active'));
  const page=document.getElementById('page_'+id);
  if(page)page.classList.add('active');
  const link=document.querySelector(`[data-page="${id}"]`);
  if(link)link.classList.add('active');
  // Load data for settings pages
  if(id==='settings_general')loadGeneral();
  if(id==='settings_models')loadModels();
  if(id==='settings_voices')loadVoices();
  if(id==='settings_env')loadEnvironment();
  if(id==='settings_visual')loadVisual();
  if(id==='storage')loadStorage();
  if(id==='plugins')loadPlugins();
  if(id==='new_station'&&!wizEditMode)resetWizard();
}

// ═══ Toast ═══
function toast(msg){
  const old=document.querySelector('.toast');if(old)old.remove();
  const el=document.createElement('div');el.className='toast';el.textContent=msg;
  document.body.appendChild(el);setTimeout(()=>el.remove(),4000);
}
function esc(s){const d=document.createElement('div');d.textContent=s||'';return d.innerHTML;}
function fmtUp(s){if(!s)return'';if(s<60)return s+'s';if(s<3600)return Math.floor(s/60)+'m';return Math.floor(s/3600)+'h '+Math.floor((s%3600)/60)+'m';}
function fmtBytes(b){if(b<1024)return b+'B';if(b<1048576)return(b/1024).toFixed(1)+'KB';return(b/1048576).toFixed(1)+'MB';}

// ═══ Stations (Home) ═══
async function fetchStations(){
  try{
    const r=await fetch(API+'/api/stations');const d=await r.json();
    stations=d.stations||[];renderStations();
    document.getElementById('serverInfo').textContent=stations.length+' stations · OK';
  }catch(e){document.getElementById('serverInfo').textContent='Error';
    document.getElementById('stationGrid').innerHTML='<p style="color:var(--danger)">Cannot reach server.</p>';}
}
function renderStations(){
  const g=document.getElementById('stationGrid');
  if(!stations.length){g.innerHTML='<p style="color:var(--muted)">No stations. Create one!</p>';return;}
  g.innerHTML=stations.map(s=>`
    <div class="station-card ${s.running?'running':''}" onclick="viewStation('${s.station_id}')">
      <span class="badge ${s.running?'live':'idle'}">${s.running?'● LIVE':'○ Idle'}</span>
      <div class="name">${esc(s.name)}</div>
      <div class="cat">${esc(s.category||s.meta_plugin)}</div>
      <div class="meta">${s.host?'Host: '+esc(s.host)+' · ':''}ID: ${esc(s.station_id)}${s.running?' · PID '+s.pid+' · '+fmtUp(s.uptime_sec):''}</div>
      <div class="actions" onclick="event.stopPropagation()">
        ${s.running
          ?`<button class="btn btn-secondary btn-sm" onclick="window.location='/runtime/${s.station_id}'">📡 Runtime</button>
            <button class="btn btn-danger btn-sm" onclick="stopStation('${s.station_id}')">⏹ Stop</button>`
          :`<button class="btn btn-primary btn-sm" onclick="launchStation('${s.station_id}')">▶ Launch</button>`}
        <button class="btn btn-secondary btn-sm" onclick="editStation('${s.station_id}')">✏️</button>
        <button class="btn btn-danger btn-sm" onclick="deleteStation('${s.station_id}')">🗑️</button>
      </div>
    </div>`).join('');
}
async function launchStation(id){
  toast('Launching '+id+'... (may take a moment)');
  try{const r=await fetch(API+'/api/stations/'+id+'/launch',{method:'POST'});const d=await r.json();
    if(d.status==='error'){
      toast('⚠️ '+id+': '+(d.message||'unknown error'));
      if(d.output){activeStation=id;document.getElementById('runtimeTitle').textContent='Launch Error: '+id;document.getElementById('runtimePanel').style.display='block';document.getElementById('runtimeLog').textContent=d.output;}
    }else{toast(d.status+': '+id);if(d.status==='launched'){setTimeout(()=>window.location='/runtime/'+id,2000);}}
    setTimeout(fetchStations,1000);}catch(e){toast('Failed: '+e.message);}
}
async function stopStation(id){
  try{await fetch(API+'/api/stations/'+id+'/stop',{method:'POST'});toast('Stopped '+id);
    if(activeStation===id){activeStation=null;document.getElementById('runtimePanel').style.display='none';clearInterval(logInterval);}
    setTimeout(fetchStations,500);}catch(e){toast('Failed: '+e.message);}
}
async function deleteStation(id){
  if(!confirm('Delete station "'+id+'"? This cannot be undone.'))return;
  try{const r=await fetch(API+'/api/stations/'+id,{method:'DELETE'});const d=await r.json();
    toast(d.status+': '+id);fetchStations();}catch(e){toast('Delete failed: '+e.message);}
}
function viewStation(id){
  activeStation=id;const s=stations.find(x=>x.station_id===id);
  document.getElementById('runtimeTitle').textContent=s?s.name:id;
  document.getElementById('runtimePanel').style.display='block';
  refreshLog();clearInterval(logInterval);logInterval=setInterval(refreshLog,3000);
  connectAudio(id);
}
async function refreshLog(){
  if(!activeStation)return;
  try{const r=await fetch(API+'/api/stations/'+activeStation+'/log?lines=80');const d=await r.json();
    const el=document.getElementById('runtimeLog');el.textContent=d.log||'No logs.';el.scrollTop=el.scrollHeight;}catch(e){}
}
function openStationUI(){
  if(!activeStation)return;
  window.location='/runtime/'+activeStation;
}
function stopActive(){if(activeStation)stopStation(activeStation);}

// ═══ Edit Station ═══
async function editStation(id){
  wizEditMode=true;wizEditId=id;
  document.getElementById('wizardTitle').textContent='Edit Station: '+id;
  document.getElementById('wizardSubtitle').textContent='Modify station configuration';
  document.getElementById('wizFinishBtn').textContent='💾 Save Changes';
  try{
    const r=await fetch(API+'/api/stations/'+id+'/manifest');const m=await r.json();
    await loadWizardData();
    const st=m.station||{};
    document.getElementById('wz_id').value=id;document.getElementById('wz_id').disabled=true;
    document.getElementById('wz_name').value=st.name||id;
    document.getElementById('wz_category').value=st.category||'';
    document.getElementById('wz_host').value=st.host||'';
    document.getElementById('wz_logo').value=st.logo||'';
    setSelectVal('wz_meta_plugin',m.meta_plugin||'radio_station');
    setSelectVal('wz_llm_provider',(m.llm||{}).provider||'ollama');
    document.getElementById('wz_llm_endpoint').value=(m.llm||{}).endpoint||'';
    document.getElementById('wz_model_producer').value=(m.models||{}).producer||'';
    document.getElementById('wz_model_host').value=(m.models||{}).host||'';
    document.getElementById('wz_model_nav').value=(m.models||{}).navigator||'';
    document.getElementById('wz_model_embedding').value=(m.models||{}).embedding||'';
    document.getElementById('wz_embedding_enabled').checked=!!((m.embedding||{}).enabled);
    setSelectVal('wz_voices_provider',(m.audio||{}).voices_provider||'kokoro');
    document.getElementById('wz_piper_bin').value=(m.audio||{}).piper_bin||'';
    wizChars=(m.characters&&Object.keys(m.characters).length)?JSON.parse(JSON.stringify(m.characters)):{host:{role:'moderator',traits:['calm'],focus:['flow']}};
    wizFeeds=m.feeds?JSON.parse(JSON.stringify(m.feeds)):{};
    wizMixWeights=(m.mix||{}).weights?JSON.parse(JSON.stringify((m.mix||{}).weights)):{};
    wizSchedulerQuotas=(m.scheduler||{}).source_quotas?JSON.parse(JSON.stringify((m.scheduler||{}).source_quotas)):{};
    // Load voice assignments
    if(m.voices&&typeof m.voices==='object'){
      window._wizVoices=JSON.parse(JSON.stringify(m.voices));
    }else{window._wizVoices={};}
    renderFeeds();renderCharacters();renderVoiceAssignments();renderMixWeights();renderSchedulerQuotas();
    showPage('new_station');wizTab(0);
  }catch(e){toast('Failed to load station: '+e.message);}
}
function setSelectVal(id,val){const el=document.getElementById(id);if(el){el.value=val;if(!el.value){const o=document.createElement('option');o.value=val;o.textContent=val;el.appendChild(o);el.value=val;}}}

// ═══ Wizard ═══
async function loadWizardData(){
  try{
    const[pl,mp,vc]=await Promise.all([
      fetch(API+'/api/plugins').then(r=>r.json()),
      fetch(API+'/api/meta_plugins').then(r=>r.json()),
      fetch(API+'/api/voices').then(r=>r.json())
    ]);
    wizPlugins=pl.plugins||{};wizMeta=mp.meta_plugins||[];wizVoices=vc.voices||[];
    // Populate meta plugin dropdown
    const sel=document.getElementById('wz_meta_plugin');sel.innerHTML='';
    wizMeta.forEach(m=>{const o=document.createElement('option');o.value=m;o.textContent=m;sel.appendChild(o);});
  }catch(e){console.warn('loadWizardData:',e);}
}
async function resetWizard(){
  wizEditMode=false;wizEditId='';
  document.getElementById('wizardTitle').textContent='New Station';
  document.getElementById('wizardSubtitle').textContent='Create a new radio station';
  document.getElementById('wizFinishBtn').textContent='✅ Create Station';
  document.getElementById('wz_id').value='';document.getElementById('wz_id').disabled=false;
  document.getElementById('wz_name').value='';document.getElementById('wz_category').value='';
  document.getElementById('wz_host').value='';document.getElementById('wz_logo').value='';
  wizChars={host:{role:'moderator',traits:['calm','smart'],focus:['flow','continuity']}};
  wizFeeds={};wizMixWeights={};wizSchedulerQuotas={};
  window._wizVoices={};
  await loadWizardData();
  // Load global defaults
  try{
    const mdl=await fetch(API+'/api/settings/models').then(r=>r.json());
    const vc=await fetch(API+'/api/settings/voices').then(r=>r.json());
    setSelectVal('wz_llm_provider',mdl.provider||'ollama');
    document.getElementById('wz_llm_endpoint').value=mdl.llm_endpoint||'http://127.0.0.1:11434/api/generate';
    document.getElementById('wz_model_producer').value=mdl.producer_model||'gpt-4o';
    document.getElementById('wz_model_host').value=mdl.host_model||'gpt-4o';
    setSelectVal('wz_voices_provider',vc.provider||'kokoro');
    document.getElementById('wz_piper_bin').value=vc.piper_bin||'';
  }catch(e){}
  // Initialize feeds from plugins
  Object.entries(wizPlugins).forEach(([k,v])=>{if(v.is_feed){wizFeeds[k]=v.defaults?JSON.parse(JSON.stringify(v.defaults)):{enabled:false};wizFeeds[k].enabled=wizFeeds[k].enabled!==undefined?wizFeeds[k].enabled:false;}});
  renderFeeds();renderCharacters();renderVoiceAssignments();renderMixWeights();renderSchedulerQuotas();
  wizTab(0);
}
function wizTab(i){
  currentWizTab=i;
  document.querySelectorAll('#wizardTabs button').forEach((b,j)=>b.classList.toggle('active',j===i));
  for(let j=0;j<6;j++)document.getElementById('wiz_'+j).classList.toggle('active',j===i);
  if(i===3)renderVoiceAssignments();
  if(i===4){renderMixWeights();renderSchedulerQuotas();}
  if(i===5)refreshWizPreview();
}
function wizPrev(){if(currentWizTab>0)wizTab(currentWizTab-1);}
function wizNext(){if(currentWizTab<5)wizTab(currentWizTab+1);}

// Feeds
function renderFeeds(){
  const el=document.getElementById('feedsList');
  const feeds=Object.entries(wizPlugins).filter(([k,v])=>v.is_feed);
  if(!feeds.length){el.innerHTML='<p style="color:var(--muted)">No feed plugins found.</p>';return;}
  el.innerHTML=feeds.map(([k,v])=>{
    const cfg=wizFeeds[k]||{};const en=!!cfg.enabled;
    const fields=v.defaults?Object.entries(v.defaults).filter(([fk])=>fk!=='enabled').map(([fk,fv])=>{
      const val=cfg[fk]!==undefined?cfg[fk]:fv;
      const isArr=Array.isArray(fv);
      return`<div class="form-group" style="flex:1;min-width:180px"><label>${fk}</label><input data-feed="${k}" data-key="${fk}" value="${esc(isArr?JSON.stringify(val):String(val))}" style="width:100%"></div>`;
    }).join(''):'';
    return`<div class="card-section" style="margin-bottom:8px;padding:12px 16px;border:1px solid ${en?'var(--good)':'#333'};border-radius:8px">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:${fields?'8':'0'}px">
        <label class="toggle" style="margin:0"><input type="checkbox" ${en?'checked':''} onchange="toggleFeed('${k}',this.checked)"><span style="font-weight:600">${esc(v.display||k)}</span></label>
        <span class="tag">${k}</span><span style="font-size:11px;color:var(--muted)">${esc(v.desc||'')}</span>
      </div>
      ${fields?'<div class="form-row" style="flex-wrap:wrap">'+fields+'</div>':''}
    </div>`;
  }).join('');
}
function toggleFeed(k,en){wizFeeds[k]=wizFeeds[k]||{};wizFeeds[k].enabled=en;renderFeeds();}
function collectFeedValues(){
  document.querySelectorAll('[data-feed]').forEach(el=>{
    const k=el.dataset.feed,fk=el.dataset.key;let v=el.value;
    try{v=JSON.parse(v);}catch(e){}
    wizFeeds[k]=wizFeeds[k]||{};wizFeeds[k][fk]=v;
  });
}

// Characters
const ROLES=['host','engineer','skeptic','macro','optimist','coach','analyst','stats_guru','hype','moderator','narrator','risk_manager'];
const TRAITS=['calm','smart','technical','precise','critical','grounded','energetic','constructive','curious','skeptical','creative','data_driven'];
const FOCUS=['flow','continuity','systems','signals','risk','opportunity','growth','discipline','positioning','execution','macro','narrative','pacing','metrics','trends','strategy'];
function renderCharacters(){
  const el=document.getElementById('charsList');
  el.innerHTML=Object.entries(wizChars).map(([name,c])=>`
    <div class="card-section" style="margin-bottom:8px;padding:12px 16px;border-radius:8px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
        <strong>${esc(name)}</strong>
        ${name!=='host'?`<button class="btn btn-danger btn-sm" onclick="removeChar('${name}')">✕</button>`:''}
      </div>
      <div class="form-row">
        <div class="form-group"><label>Role</label><select onchange="wizChars['${name}'].role=this.value">${ROLES.map(r=>`<option ${c.role===r?'selected':''}>${r}</option>`).join('')}</select></div>
        <div class="form-group"><label>Traits (comma-sep)</label><input value="${(c.traits||[]).join(', ')}" onchange="wizChars['${name}'].traits=this.value.split(',').map(s=>s.trim()).filter(Boolean)"></div>
        <div class="form-group"><label>Focus (comma-sep)</label><input value="${(c.focus||[]).join(', ')}" onchange="wizChars['${name}'].focus=this.value.split(',').map(s=>s.trim()).filter(Boolean)"></div>
      </div>
    </div>`).join('');
}
function addCharacter(){
  const name=prompt('Character name (lowercase, e.g. "analyst"):');
  if(!name)return;const k=name.trim().toLowerCase().replace(/\\s+/g,'_');
  if(wizChars[k]){toast('Character "'+k+'" already exists');return;}
  wizChars[k]={role:'analyst',traits:['smart'],focus:['signals']};renderCharacters();
}
function removeChar(k){delete wizChars[k];renderCharacters();}

// Voice assignments
function renderVoiceAssignments(){
  const el=document.getElementById('voiceAssignments');
  const voices=window._wizVoices||{};
  el.innerHTML='<h4 style="margin:12px 0 8px;font-size:13px">Character → Voice Model</h4>'+
    Object.keys(wizChars).map(k=>`<div class="form-group"><label>${k}</label><input id="wz_voice_${k}" value="${esc(voices[k]||'')}" placeholder="voice model path or ID"></div>`).join('');
}

// Mix weights & quotas
function renderMixWeights(){
  const el=document.getElementById('mixWeights');
  const enabled=Object.keys(wizFeeds).filter(k=>(wizFeeds[k]||{}).enabled);
  if(!enabled.length){el.innerHTML='<p style="color:var(--muted)">No feeds enabled.</p>';return;}
  el.innerHTML=enabled.map(k=>`<div class="form-group" style="display:flex;align-items:center;gap:10px">
    <label style="width:140px;margin:0">${k}</label>
    <input type="number" step="0.05" min="0" max="1" value="${wizMixWeights[k]||0.1}" style="width:80px" onchange="wizMixWeights['${k}']=parseFloat(this.value)">
  </div>`).join('');
}
function renderSchedulerQuotas(){
  const el=document.getElementById('schedQuotas');
  const enabled=Object.keys(wizFeeds).filter(k=>(wizFeeds[k]||{}).enabled);
  if(!enabled.length){el.innerHTML='<p style="color:var(--muted)">No feeds enabled.</p>';return;}
  el.innerHTML=enabled.map(k=>`<div class="form-group" style="display:flex;align-items:center;gap:10px">
    <label style="width:140px;margin:0">${k}</label>
    <input type="number" min="1" max="50" value="${wizSchedulerQuotas[k]||3}" style="width:80px" onchange="wizSchedulerQuotas['${k}']=parseInt(this.value)">
  </div>`).join('');
}

// Build manifest
function buildManifest(){
  collectFeedValues();
  const m={};
  m.station={id:document.getElementById('wz_id').value.trim(),name:document.getElementById('wz_name').value.trim()||'Station',
    host:document.getElementById('wz_host').value.trim()||'Host',category:document.getElementById('wz_category').value.trim()||'Custom',
    logo:document.getElementById('wz_logo').value.trim()};
  m.meta_plugin=document.getElementById('wz_meta_plugin').value||'radio_station';
  m.llm={provider:document.getElementById('wz_llm_provider').value,endpoint:document.getElementById('wz_llm_endpoint').value};
  m.models={producer:document.getElementById('wz_model_producer').value,host:document.getElementById('wz_model_host').value,
    navigator:document.getElementById('wz_model_nav').value,embedding:document.getElementById('wz_model_embedding').value};
  m.embedding={enabled:document.getElementById('wz_embedding_enabled').checked};
  m.audio={voices_provider:document.getElementById('wz_voices_provider').value,piper_bin:document.getElementById('wz_piper_bin').value};
  // Voices
  const voices={};Object.keys(wizChars).forEach(k=>{const el=document.getElementById('wz_voice_'+k);voices[k]=el?el.value:'';});
  m.voices=voices;
  m.characters=JSON.parse(JSON.stringify(wizChars));
  m.feeds=JSON.parse(JSON.stringify(wizFeeds));
  // Mix
  const enabledFeeds=Object.keys(wizFeeds).filter(k=>(wizFeeds[k]||{}).enabled);
  const weights={};enabledFeeds.forEach(k=>{weights[k]=wizMixWeights[k]||0.1;});
  m.mix={weights};
  const quotas={};enabledFeeds.forEach(k=>{quotas[k]=wizSchedulerQuotas[k]||3;});
  m.scheduler={source_quotas:quotas};
  m.paths={db:'station.sqlite',memory:'station_memory.json'};
  return m;
}
function refreshWizPreview(){
  try{const m=buildManifest();
    document.getElementById('wizPreview').textContent=JSON.stringify(m,null,2);
  }catch(e){document.getElementById('wizPreview').textContent='Error: '+e.message;}
}
async function wizSave(){
  try{
    const m=buildManifest();const id=wizEditMode?wizEditId:m.station.id;
    if(!id){toast('Station ID required');return;}
    const r=await fetch(API+'/api/stations/'+id+'/manifest',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(m)});
    const d=await r.json();toast('Saved: '+id);fetchStations();
  }catch(e){toast('Save failed: '+e.message);}
}
async function wizFinish(){
  try{
    const m=buildManifest();const id=wizEditMode?wizEditId:m.station.id;
    if(!id){toast('Station ID required');return;}
    if(wizEditMode){
      await fetch(API+'/api/stations/'+id+'/manifest',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(m)});
    }else{
      const r=await fetch(API+'/api/stations/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({station_id:id,manifest:m})});
      const d=await r.json();if(d.error){toast(d.error);return;}
    }
    toast((wizEditMode?'Saved':'Created')+': '+id);
    wizEditMode=false;document.getElementById('wz_id').disabled=false;
    showPage('home');fetchStations();
  }catch(e){toast('Failed: '+e.message);}
}

// ═══ Settings: General ═══
async function loadGeneral(){
  try{const d=await fetch(API+'/api/settings/general').then(r=>r.json());
    document.getElementById('set_auto_start').checked=!!d.auto_start_last_station;
    document.getElementById('set_always_server').checked=!!d.always_launch_server;
    document.getElementById('set_web_port').value=d.web_server_port||7800;
    document.getElementById('set_poll_ms').value=d.status_poll_ms||1000;
    if(d.theme)setSelectVal('set_theme',d.theme);
    document.getElementById('set_scale').value=d.ui_scale||1.0;
  }catch(e){}
}
async function saveGeneral(){
  const d={auto_start_last_station:document.getElementById('set_auto_start').checked,
    always_launch_server:document.getElementById('set_always_server').checked,
    web_server_port:parseInt(document.getElementById('set_web_port').value)||7800,
    status_poll_ms:parseInt(document.getElementById('set_poll_ms').value)||1000,
    theme:document.getElementById('set_theme').value,
    ui_scale:parseFloat(document.getElementById('set_scale').value)||1.0};
  await fetch(API+'/api/settings/general',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)});
  toast('General settings saved!');
}

// ═══ Settings: Models ═══
async function loadModels(){
  try{const d=await fetch(API+'/api/settings/models').then(r=>r.json());
    setSelectVal('mdl_provider',d.provider||'ollama');
    document.getElementById('mdl_endpoint').value=d.llm_endpoint||'';
    document.getElementById('mdl_producer').value=d.producer_model||'';
    document.getElementById('mdl_host').value=d.host_model||'';
    document.getElementById('mdl_anthropic_key').value=d.anthropic_api_key||'';
    document.getElementById('mdl_openai_key').value=d.openai_api_key||'';
    document.getElementById('mdl_google_key').value=d.google_api_key||'';
  }catch(e){}
}
async function saveModels(){
  const d={provider:document.getElementById('mdl_provider').value,llm_endpoint:document.getElementById('mdl_endpoint').value,
    producer_model:document.getElementById('mdl_producer').value,host_model:document.getElementById('mdl_host').value,
    anthropic_api_key:document.getElementById('mdl_anthropic_key').value,openai_api_key:document.getElementById('mdl_openai_key').value,
    google_api_key:document.getElementById('mdl_google_key').value};
  await fetch(API+'/api/settings/models',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)});
  toast('Model settings saved!');
}

// ═══ Settings: Voices ═══
async function loadVoices(){
  try{const d=await fetch(API+'/api/settings/voices').then(r=>r.json());
    setSelectVal('vc_provider',d.provider||'kokoro');
    document.getElementById('vc_piper_bin').value=d.piper_bin||'';
    document.getElementById('vc_api_key').value=d.api_key||'';
    document.getElementById('vc_voices_dir').value=d.voices_directory||'';
    document.getElementById('vc_host').value=d.voice_host||'';
    document.getElementById('vc_expert').value=d.voice_expert||'';
    document.getElementById('vc_skeptic').value=d.voice_skeptic||'';
    document.getElementById('vc_optimist').value=d.voice_optimist||'';
    document.getElementById('vc_coach').value=d.voice_coach||'';
  }catch(e){}
}
async function saveVoices(){
  const d={provider:document.getElementById('vc_provider').value,piper_bin:document.getElementById('vc_piper_bin').value,
    api_key:document.getElementById('vc_api_key').value,voices_directory:document.getElementById('vc_voices_dir').value,
    voice_host:document.getElementById('vc_host').value,voice_expert:document.getElementById('vc_expert').value,
    voice_skeptic:document.getElementById('vc_skeptic').value,voice_optimist:document.getElementById('vc_optimist').value,
    voice_coach:document.getElementById('vc_coach').value};
  await fetch(API+'/api/settings/voices',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)});
  toast('Voice settings saved!');
}

// ═══ Settings: Environment ═══
let envVars={};
async function loadEnvironment(){
  try{envVars=await fetch(API+'/api/settings/environment').then(r=>r.json());renderEnvVars();}catch(e){}
}
function renderEnvVars(){
  const el=document.getElementById('envVarsList');
  const entries=Object.entries(envVars);
  if(!entries.length){el.innerHTML='<p style="color:var(--muted)">No environment variables set. Click + to add.</p>';return;}
  el.innerHTML=entries.map(([k,v])=>`<div class="form-row" style="margin-bottom:6px;align-items:end">
    <div class="form-group" style="flex:0 0 200px"><label>Name</label><input value="${esc(k)}" data-env-key="${k}" class="env-key" style="font-family:monospace"></div>
    <div class="form-group" style="flex:1"><label>Value</label><input value="${esc(v)}" data-env-val="${k}" class="env-val" type="password" onfocus="this.type='text'" onblur="this.type='password'"></div>
    <button class="btn btn-danger btn-sm" onclick="delete envVars['${k}'];renderEnvVars()">✕</button>
  </div>`).join('');
}
function addEnvVar(){const k=prompt('Variable name:');if(!k)return;envVars[k.trim()]='';;renderEnvVars();}
async function saveEnvironment(){
  // Collect from UI
  const collected={};
  document.querySelectorAll('.env-key').forEach(el=>{const k=el.value.trim();const v=document.querySelector(`[data-env-val="${el.dataset.envKey}"]`);if(k&&v)collected[k]=v.value;});
  await fetch(API+'/api/settings/environment',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(collected)});
  envVars=collected;toast('Environment saved!');
}
async function resetEnvironment(){
  if(!confirm('Clear all environment variables?'))return;
  await fetch(API+'/api/settings/environment',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({})});
  envVars={};renderEnvVars();toast('Environment reset.');
}

// ═══ Settings: Visual Models ═══
async function loadVisual(){
  try{const d=await fetch(API+'/api/settings/visual_models').then(r=>r.json());
    setSelectVal('vis_type',d.model_type||'local');
    document.getElementById('vis_local').value=d.local_model||'';
    setSelectVal('vis_api_prov',d.api_provider||'');
    document.getElementById('vis_api_model').value=d.api_model||'';
    document.getElementById('vis_api_key').value=d.api_key||'';
    document.getElementById('vis_api_endpoint').value=d.api_endpoint||'';
    document.getElementById('vis_max_size').value=d.max_image_size||1024;
    setSelectVal('vis_quality',d.image_quality||'low');
  }catch(e){}
}
async function saveVisual(){
  const d={model_type:document.getElementById('vis_type').value,local_model:document.getElementById('vis_local').value,
    api_provider:document.getElementById('vis_api_prov').value,api_model:document.getElementById('vis_api_model').value,
    api_key:document.getElementById('vis_api_key').value,api_endpoint:document.getElementById('vis_api_endpoint').value,
    max_image_size:document.getElementById('vis_max_size').value,image_quality:document.getElementById('vis_quality').value};
  await fetch(API+'/api/settings/visual_models',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)});
  toast('Visual model settings saved!');
}

// ═══ Storage ═══
async function loadStorage(){
  try{const d=await fetch(API+'/api/storage/info').then(r=>r.json());
    document.getElementById('configPaths').innerHTML='Global config: <code>'+esc(d.config_path)+'</code><br>Stations: <code>'+esc(d.stations_dir)+'</code>';
    const sizes=d.station_sizes||{};
    document.getElementById('diskUsage').innerHTML=Object.entries(sizes).map(([k,v])=>`<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid #222"><span>${esc(k)}</span><span style="color:var(--muted)">${fmtBytes(v)}</span></div>`).join('')||'<p style="color:var(--muted)">No stations.</p>';
  }catch(e){document.getElementById('diskUsage').innerHTML='<p style="color:var(--danger)">Failed to load.</p>';}
}
async function clearAllLogs(){
  if(!confirm('Delete ALL runtime logs?'))return;
  const r=await fetch(API+'/api/storage/clear_logs',{method:'POST'});const d=await r.json();
  toast('Cleared '+d.count+' log(s)');
}
async function vacuumDatabases(){
  if(!confirm('Optimize all databases?'))return;
  const r=await fetch(API+'/api/storage/vacuum_databases',{method:'POST'});const d=await r.json();
  toast('Vacuumed '+d.count+' database(s)');
}

// ═══ Plugins ═══
async function loadPlugins(){
  try{const d=await fetch(API+'/api/plugins').then(r=>r.json());
    const el=document.getElementById('pluginsList');
    const plugins=Object.entries(d.plugins||{});
    if(!plugins.length){el.innerHTML='<p style="color:var(--muted)">No plugins found in plugins/ directory.</p>';return;}
    el.innerHTML=plugins.map(([k,v])=>`<div class="card-section" style="margin-bottom:8px">
      <div style="display:flex;align-items:center;gap:10px">
        <strong>${esc(v.display||k)}</strong>
        <span class="tag">${v.is_feed?'feed':'widget'}</span>
        <span class="tag">${k}.py</span>
      </div>
      ${v.desc?'<p style="font-size:12px;color:var(--muted);margin-top:4px">'+esc(v.desc)+'</p>':''}
    </div>`).join('');
  }catch(e){document.getElementById('pluginsList').innerHTML='<p style="color:var(--danger)">Failed to load plugins.</p>';}
}

// ═══ Audio WebSocket ═══
let audioWs=null,audioCtx=null,audioQueue=[],audioPlaying=false;
function connectAudio(stationId){
  if(audioWs)try{audioWs.close();}catch(e){}
  const proto=location.protocol==='https:'?'wss:':'ws:';
  audioWs=new WebSocket(proto+'//'+location.host+'/ws/audio/'+stationId);
  audioWs.binaryType='arraybuffer';
  audioWs.onopen=()=>{document.getElementById('audioBar').classList.add('active');document.getElementById('nowPlaying').textContent='🎙️ '+stationId;setInterval(()=>{if(audioWs.readyState===1)audioWs.send('ping');},15000);};
  audioWs.onmessage=(evt)=>{if(typeof evt.data==='string')return;try{const buf=evt.data;const view=new DataView(buf);const ml=view.getUint32(0,false);const mb=new Uint8Array(buf,4,ml);const meta=JSON.parse(new TextDecoder().decode(mb));const wav=buf.slice(4+ml);if(meta.voice&&meta.text)document.getElementById('subtitle').textContent=meta.voice.toUpperCase()+': '+meta.text;audioQueue.push(wav);if(!audioPlaying)playNext();}catch(e){console.error('[Audio] parse error:',e);}};
  audioWs.onclose=()=>{document.getElementById('audioBar').classList.remove('active');};
}
function playNext(){
  if(!audioQueue.length){audioPlaying=false;return;}audioPlaying=true;
  if(!audioCtx){audioCtx=new(window.AudioContext||window.webkitAudioContext)();}
  if(audioCtx.state==='suspended')audioCtx.resume();
  const wav=audioQueue.shift();audioCtx.decodeAudioData(wav.slice(0),d=>{const s=audioCtx.createBufferSource();s.buffer=d;s.connect(audioCtx.destination);s.onended=playNext;s.start(0);},e=>{console.error('[Audio] decode failed:',e);playNext();});
}

// ═══ Init ═══
fetchStations();setInterval(fetchStations,5000);
</script>
</body>
</html>"""


# ═══════════════════════════════════════════════════════════════════════════
# Runtime Dashboard HTML — web equivalent of bookmark.py's tkinter StationUI
# ═══════════════════════════════════════════════════════════════════════════

_RUNTIME_DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{STATION_NAME}} — Radio OS Runtime</title>
<style>
:root{--bg:#0e0e0e;--surface:#141414;--surface2:#1a1a1a;--border:#2a2a2a;--text:#e0e0e0;--muted:#888;--accent:#4cc9f0;--danger:#ff4757;--success:#2ed573;--warn:#ffa502;--font:'Segoe UI','Helvetica Neue',Arial,sans-serif}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);color:var(--text);font-family:var(--font);display:flex;flex-direction:column;height:100vh;overflow:hidden}

/* ── Top bar ── */
.topbar{display:flex;align-items:center;gap:12px;padding:8px 16px;background:var(--surface);border-bottom:1px solid var(--border);min-height:48px;flex-shrink:0}
.topbar .logo{font-size:22px;cursor:pointer}
.topbar .station-name{font-size:16px;font-weight:600;flex:1}
.topbar .meta{font-size:11px;color:var(--muted)}
.topbar .badge{display:inline-block;padding:2px 8px;border-radius:10px;font-size:10px;font-weight:600;text-transform:uppercase}
.badge.live{background:rgba(46,213,115,.15);color:var(--success)}
.badge.offline{background:rgba(136,136,136,.15);color:var(--muted)}
.btn{padding:4px 12px;border:1px solid var(--border);background:var(--surface2);color:var(--text);border-radius:6px;cursor:pointer;font-size:12px;display:inline-flex;align-items:center;gap:4px}
.btn:hover{background:#222}
.btn.danger{border-color:var(--danger);color:var(--danger)}
.btn.danger:hover{background:rgba(255,71,87,.15)}
.btn.accent{border-color:var(--accent);color:var(--accent)}
.btn.accent:hover{background:rgba(76,201,240,.1)}

/* ── Main content area ── */
.main-area{display:flex;flex:1;overflow:hidden}

/* ── Left panel: Tabbed content ── */
.left-panel{flex:1;display:flex;flex-direction:column;border-right:1px solid var(--border);min-width:0}
.tab-bar{display:flex;align-items:center;background:var(--surface);border-bottom:1px solid var(--border);flex-shrink:0;padding:0 4px}
.tab-btn{padding:8px 16px;font-size:12px;font-weight:600;color:var(--muted);background:none;border:none;border-bottom:2px solid transparent;cursor:pointer;transition:all .15s;display:inline-flex;align-items:center;gap:5px}
.tab-btn:hover{color:var(--text);background:rgba(255,255,255,.03)}
.tab-btn.active{color:var(--accent);border-bottom-color:var(--accent)}
.tab-content{display:none;flex:1;flex-direction:column;overflow:hidden;min-height:0}
.tab-content.active{display:flex}

/* ── Waveform tab ── */
.waveform-wrap{flex:1;display:flex;flex-direction:column;background:var(--bg);position:relative;overflow:hidden}
.waveform-canvas{width:100%;flex:1;display:block}
.waveform-info{position:absolute;bottom:10px;left:16px;font-size:11px;color:var(--muted);pointer-events:none;display:flex;gap:16px}
.waveform-info span{background:rgba(14,14,14,.7);padding:2px 8px;border-radius:4px}
.waveform-idle{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:8px;color:var(--muted);font-size:14px;pointer-events:none}
.waveform-idle .icon{font-size:48px;opacity:.3}

/* ── Log tab ── */
.log-panel{flex:1;display:flex;flex-direction:column;min-width:0}
.log-header{display:flex;align-items:center;gap:8px;padding:8px 12px;background:var(--surface);border-bottom:1px solid var(--border);flex-shrink:0}
.log-header h3{font-size:13px;font-weight:600;flex:1}
.log-header .filter{padding:2px 8px;font-size:11px;background:var(--bg);border:1px solid var(--border);border-radius:4px;color:var(--text);outline:none}
.log-content{flex:1;overflow-y:auto;padding:8px 12px;font-family:'Menlo','Consolas','Courier New',monospace;font-size:11.5px;line-height:1.6;white-space:pre-wrap;word-wrap:break-word;background:var(--bg)}
.log-content .line-ts{color:var(--muted)}
.log-content .line-feed{color:#7bed9f}
.log-content .line-audio{color:var(--accent)}
.log-content .line-err{color:var(--danger)}
.log-content .line-web{color:#a29bfe}
.log-content .line-ftb{color:#ffa502}
.log-content .line-dj{color:#ff6b81}

/* ── Right panel: Info ── */
.info-panel{width:320px;display:flex;flex-direction:column;overflow-y:auto;flex-shrink:0}
.info-section{padding:12px;border-bottom:1px solid var(--border)}
.info-section h4{font-size:12px;font-weight:600;text-transform:uppercase;color:var(--muted);margin-bottom:8px;letter-spacing:.5px}
.info-row{display:flex;justify-content:space-between;padding:4px 0;font-size:12px}
.info-row .label{color:var(--muted)}
.info-row .value{font-weight:500;text-align:right;max-width:60%;word-break:break-all}

/* Plugin links */
.plugin-link{display:block;padding:6px 10px;margin:3px 0;background:var(--surface2);border:1px solid var(--border);border-radius:6px;color:var(--text);text-decoration:none;font-size:12px;transition:all .15s}
.plugin-link:hover{border-color:var(--accent);background:rgba(76,201,240,.05)}

/* ── Bottom: Audio bar + subtitle ── */
.audio-section{flex-shrink:0;border-top:1px solid var(--border);background:var(--surface)}
.subtitle-bar{padding:10px 16px;min-height:40px;display:flex;align-items:center;justify-content:center;font-size:14px;font-weight:500;color:var(--accent);text-align:center;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.subtitle-bar:empty::after{content:'Waiting for audio...';color:var(--muted);font-size:12px;font-weight:400}
.audio-controls{display:flex;align-items:center;gap:10px;padding:6px 16px;border-top:1px solid var(--border);background:var(--bg)}
.audio-controls .status{font-size:11px;color:var(--muted);flex:1}
.audio-controls .status.connected{color:var(--success)}
.audio-controls .status.error{color:var(--danger)}
.volume-slider{width:80px;accent-color:var(--accent)}
.play-btn{width:32px;height:32px;border-radius:50%;background:var(--accent);border:none;color:#000;font-size:14px;cursor:pointer;display:flex;align-items:center;justify-content:center;flex-shrink:0}
.play-btn:hover{filter:brightness(1.15)}
.play-btn.muted{background:var(--muted)}

/* ── Responsive ── */
@media(max-width:768px){
  .info-panel{display:none}
  .topbar{flex-wrap:wrap;gap:6px}
}
</style>
</head>
<body>

<!-- ═══ TOP BAR ═══ -->
<div class="topbar">
  <span class="logo" onclick="window.location='/'">📻</span>
  <span class="station-name" id="stationName">{{STATION_NAME}}</span>
  <span class="badge" id="statusBadge">checking...</span>
  <span class="meta" id="uptimeMeta"></span>
  <button class="btn" onclick="window.location='/'">← Shell</button>
  <button class="btn danger" id="stopBtn" onclick="stopStation()">⏹ Stop</button>
</div>

<!-- ═══ MAIN AREA ═══ -->
<div class="main-area">

  <!-- Left: Tabbed content (Waveform + Log) -->
  <div class="left-panel">
    <div class="tab-bar">
      <button class="tab-btn active" id="tabWaveform" onclick="switchTab('waveform')">🎵 Waveform</button>
      <button class="tab-btn" id="tabConsole" onclick="switchTab('console')">📜 Console</button>
    </div>

    <!-- Tab 1: Waveform (default) -->
    <div class="tab-content active" id="panelWaveform">
      <div class="waveform-wrap">
        <canvas class="waveform-canvas" id="waveformCanvas"></canvas>
        <div class="waveform-info">
          <span id="wfSampleRate">—</span>
          <span id="wfSegInfo">Waiting for audio...</span>
        </div>
        <div class="waveform-idle" id="waveformIdle">
          <div class="icon">🎙️</div>
          <div>Waiting for audio stream...</div>
          <div style="font-size:11px;opacity:.6">Waveform will appear when playback starts</div>
        </div>
      </div>
    </div>

    <!-- Tab 2: Console Log -->
    <div class="tab-content" id="panelConsole">
      <div class="log-panel">
        <div class="log-header">
          <h3>📜 Runtime Log</h3>
          <input class="filter" id="logFilter" placeholder="Filter..." oninput="applyFilter()">
          <button class="btn" onclick="toggleAutoScroll()" id="scrollBtn">⬇ Auto-scroll</button>
          <button class="btn" onclick="refreshLog()">↻</button>
        </div>
        <div class="log-content" id="logContent">Loading...</div>
      </div>
    </div>
  </div>

  <!-- Right: Station Info -->
  <div class="info-panel">
    <div class="info-section">
      <h4>Station</h4>
      <div class="info-row"><span class="label">ID</span><span class="value">{{STATION_ID}}</span></div>
      <div class="info-row"><span class="label">Name</span><span class="value">{{STATION_NAME}}</span></div>
      <div class="info-row" id="rowCategory" style="display:none"><span class="label">Category</span><span class="value">{{STATION_CATEGORY}}</span></div>
      <div class="info-row" id="rowHost" style="display:none"><span class="label">Host</span><span class="value">{{STATION_HOST}}</span></div>
      <div class="info-row"><span class="label">PID</span><span class="value" id="infoPid">—</span></div>
      <div class="info-row"><span class="label">Uptime</span><span class="value" id="infoUptime">—</span></div>
      <div class="info-row"><span class="label">Status</span><span class="value" id="infoStatus">—</span></div>
    </div>

    <div class="info-section">
      <h4>Audio</h4>
      <div class="info-row"><span class="label">WebSocket</span><span class="value" id="infoAudioWs">disconnected</span></div>
      <div class="info-row"><span class="label">Segments played</span><span class="value" id="infoSegments">0</span></div>
      <div class="info-row"><span class="label">Queue</span><span class="value" id="infoQueue">0</span></div>
    </div>

    <div class="info-section" id="pluginLinksSection">
      <h4>Plugin Web UIs</h4>
      <div id="pluginLinks"><span style="font-size:12px;color:var(--muted)">None detected</span></div>
    </div>

    <div class="info-section">
      <h4>Actions</h4>
      <button class="btn" style="width:100%;margin-bottom:6px" onclick="refreshLog()">↻ Refresh Log</button>
      <button class="btn accent" style="width:100%;margin-bottom:6px" onclick="openManifest()">📋 View Manifest</button>
      <button class="btn danger" style="width:100%" onclick="stopStation()">⏹ Stop Station</button>
    </div>
  </div>

</div>

<!-- ═══ AUDIO SECTION ═══ -->
<div class="audio-section">
  <div class="subtitle-bar" id="subtitle"></div>
  <div class="audio-controls">
    <button class="play-btn" id="playBtn" onclick="toggleMute()">🔊</button>
    <input type="range" class="volume-slider" id="volumeSlider" min="0" max="100" value="80" oninput="setVolume(this.value)">
    <span class="status" id="audioStatus">Connecting audio...</span>
    <span style="font-size:11px;color:var(--muted)" id="segCounter"></span>
  </div>
</div>

<script>
const STATION_ID = '{{STATION_ID}}';
const API = '';
let autoScroll = true;
let logLines = [];
let filterText = '';
let segmentsPlayed = 0;

// ═══ Status polling ═══
async function pollStatus() {
  try {
    const r = await fetch(API + '/api/stations/' + STATION_ID + '/status');
    const d = await r.json();
    const badge = document.getElementById('statusBadge');
    const pid = document.getElementById('infoPid');
    const uptime = document.getElementById('infoUptime');
    const status = document.getElementById('infoStatus');
    const uptimeMeta = document.getElementById('uptimeMeta');
    if (d.status === 'running') {
      badge.textContent = '● LIVE';
      badge.className = 'badge live';
      pid.textContent = d.pid;
      uptime.textContent = fmtUp(d.uptime_sec);
      uptimeMeta.textContent = 'PID ' + d.pid + ' · ' + fmtUp(d.uptime_sec);
      status.textContent = 'Running';
      status.style.color = 'var(--success)';
      // Check for plugin web port
      if (d.web_port) {
        detectPluginUIs(d.web_port);
      }
    } else {
      badge.textContent = '○ Offline';
      badge.className = 'badge offline';
      pid.textContent = '—';
      uptime.textContent = '—';
      uptimeMeta.textContent = 'Not running';
      status.textContent = 'Stopped';
      status.style.color = 'var(--danger)';
    }
  } catch (e) {
    document.getElementById('statusBadge').textContent = 'error';
  }
}

function fmtUp(s) {
  if (!s && s !== 0) return '—';
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  return (h ? h + 'h ' : '') + (m ? m + 'm ' : '') + sec + 's';
}

// ═══ Log ═══
async function refreshLog() {
  try {
    const r = await fetch(API + '/api/stations/' + STATION_ID + '/log?lines=200');
    const d = await r.json();
    const raw = d.log || '';
    logLines = raw.split('\n');
    renderLog();
  } catch (e) {}
}

function renderLog() {
  const el = document.getElementById('logContent');
  const filter = filterText.toLowerCase();
  const filtered = filter
    ? logLines.filter(l => l.toLowerCase().includes(filter))
    : logLines;

  // Colorize log lines
  el.innerHTML = filtered.map(line => {
    let cls = '';
    const lt = line.toLowerCase();
    if (lt.includes('[feed') || lt.includes('[rss') || lt.includes('feed_worker')) cls = 'line-feed';
    else if (lt.includes('[audio') || lt.includes('headless') || lt.includes('.wav')) cls = 'line-audio';
    else if (lt.includes('error') || lt.includes('traceback') || lt.includes('exception')) cls = 'line-err';
    else if (lt.includes('[web') || lt.includes('web ui')) cls = 'line-web';
    else if (lt.includes('[ftb') || lt.includes('ftb_')) cls = 'line-ftb';
    else if (lt.includes('[dj') || lt.includes('producer')) cls = 'line-dj';
    else if (/^\[?\s*\d{2}:\d{2}/.test(line)) cls = 'line-ts';
    return '<span class="' + cls + '">' + escHtml(line) + '</span>';
  }).join('\n');

  if (autoScroll) el.scrollTop = el.scrollHeight;
}

function applyFilter() {
  filterText = document.getElementById('logFilter').value;
  renderLog();
}

function toggleAutoScroll() {
  autoScroll = !autoScroll;
  document.getElementById('scrollBtn').style.opacity = autoScroll ? '1' : '.5';
  if (autoScroll) {
    const el = document.getElementById('logContent');
    el.scrollTop = el.scrollHeight;
  }
}

function escHtml(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// ═══ Plugin UI detection ═══
let pluginUIDetected = false;
function detectPluginUIs(webPort) {
  if (pluginUIDetected) return;
  // Check runtime log for plugin web servers
  const links = [];
  for (const line of logLines) {
    const lt = line.toLowerCase();
    if (lt.includes('web server on port') || lt.includes('web ui starting on port') || lt.includes('http remote on port')) {
      // Extract port number
      const m = line.match(/port\s+(\d+)/i);
      if (m) {
        const port = m[1];
        let label = 'Plugin Web UI';
        if (lt.includes('ftb') || lt.includes('from the backmarker')) label = 'FTB Game UI';
        if (lt.includes('http remote')) label = 'FTB Remote Control';
        links.push({ label, port });
      }
    }
  }

  if (links.length > 0) {
    pluginUIDetected = true;
    // Deduplicate by port
    const seen = new Set();
    const unique = links.filter(l => { if (seen.has(l.port)) return false; seen.add(l.port); return true; });
    document.getElementById('pluginLinks').innerHTML = unique.map(l => {
      // Open directly on the station's dedicated game port (separate tab)
      // Use same hostname the user is browsing from (works over LAN / Tailscale)
      const url = location.protocol + '//' + location.hostname + ':' + l.port + '/';
      return '<a class="plugin-link" href="' + url + '" target="_blank">' +
        l.label + ' (port ' + l.port + ')</a>';
    }).join('');
  }
}

// ═══ Station control ═══
async function stopStation() {
  if (!confirm('Stop station "' + STATION_ID + '"?')) return;
  try {
    await fetch(API + '/api/stations/' + STATION_ID + '/stop', { method: 'POST' });
    // Station is dead — redirect back to shell home
    window.location = '/';
  } catch (e) {}
}

function openManifest() {
  window.open(API + '/api/stations/' + STATION_ID + '/manifest', '_blank');
}

// ═══ Audio WebSocket ═══
let audioWs = null, audioCtx = null, audioQueue = [], audioPlaying = false;
let gainNode = null, muted = false, volume = 0.8;

function connectAudio() {
  if (audioWs) try { audioWs.close(); } catch (e) {}
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  audioWs = new WebSocket(proto + '//' + location.host + '/ws/audio/' + STATION_ID);
  audioWs.binaryType = 'arraybuffer';

  audioWs.onopen = () => {
    document.getElementById('audioStatus').textContent = '● Connected';
    document.getElementById('audioStatus').className = 'status connected';
    document.getElementById('infoAudioWs').textContent = 'connected';
    document.getElementById('infoAudioWs').style.color = '#4fc3f7';
    console.log('[Audio] WebSocket connected');
    // Keepalive
    setInterval(() => { if (audioWs.readyState === 1) audioWs.send('ping'); }, 15000);
  };

  audioWs.onmessage = (evt) => {
    if (typeof evt.data === 'string') { console.log('[Audio] text msg:', evt.data); return; }
    const buf = evt.data;
    console.log('[Audio] binary frame received:', buf.byteLength, 'bytes');
    try {
      const view = new DataView(buf);
      const ml = view.getUint32(0, false);
      const mb = new Uint8Array(buf, 4, ml);
      const meta = JSON.parse(new TextDecoder().decode(mb));
      const wav = buf.slice(4 + ml);

      // Update subtitle
      if (meta.voice && meta.text) {
        document.getElementById('subtitle').textContent = meta.voice.toUpperCase() + ': ' + meta.text;
      }

      audioQueue.push(wav);
      document.getElementById('infoQueue').textContent = audioQueue.length;
      if (!audioPlaying) playNext();
    } catch (e) {
      console.error('[Audio] failed to parse frame:', e);
    }
  };

  audioWs.onclose = (evt) => {
    document.getElementById('audioStatus').textContent = '○ Disconnected — reconnecting...';
    document.getElementById('audioStatus').className = 'status error';
    document.getElementById('infoAudioWs').textContent = 'disconnected';
    document.getElementById('infoAudioWs').style.color = '';
    console.log('[Audio] WebSocket closed, code:', evt.code, 'reason:', evt.reason);
    // Auto-reconnect after 3s
    setTimeout(connectAudio, 3000);
  };

  audioWs.onerror = (evt) => {
    document.getElementById('audioStatus').textContent = '⚠ Connection error';
    document.getElementById('audioStatus').className = 'status error';
    console.error('[Audio] WebSocket error:', evt);
  };
}

// ═══ Tab switching ═══
function switchTab(tab) {
  document.getElementById('tabWaveform').className = 'tab-btn' + (tab === 'waveform' ? ' active' : '');
  document.getElementById('tabConsole').className = 'tab-btn' + (tab === 'console' ? ' active' : '');
  document.getElementById('panelWaveform').className = 'tab-content' + (tab === 'waveform' ? ' active' : '');
  document.getElementById('panelConsole').className = 'tab-content' + (tab === 'console' ? ' active' : '');
  if (tab === 'waveform') resizeCanvas();
  if (tab === 'console') { renderLog(); }
}

// ═══ Waveform visualization ═══
let analyser = null, wfAnimId = null, wfDataArray = null;
let wfActive = false;

function resizeCanvas() {
  const canvas = document.getElementById('waveformCanvas');
  const wrap = canvas.parentElement;
  canvas.width = wrap.clientWidth * (window.devicePixelRatio || 1);
  canvas.height = wrap.clientHeight * (window.devicePixelRatio || 1);
  canvas.style.width = wrap.clientWidth + 'px';
  canvas.style.height = wrap.clientHeight + 'px';
}

function startWaveform() {
  if (wfActive) return;
  wfActive = true;
  document.getElementById('waveformIdle').style.display = 'none';
  resizeCanvas();
  drawWaveform();
}

function drawWaveform() {
  const canvas = document.getElementById('waveformCanvas');
  const ctx = canvas.getContext('2d');
  const W = canvas.width, H = canvas.height;

  ctx.fillStyle = '#0e0e0e';
  ctx.fillRect(0, 0, W, H);

  // Draw grid lines
  ctx.strokeStyle = 'rgba(255,255,255,.04)';
  ctx.lineWidth = 1;
  for (let y = 0; y < H; y += H / 8) {
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke();
  }

  // Center line
  ctx.strokeStyle = 'rgba(76,201,240,.12)';
  ctx.beginPath(); ctx.moveTo(0, H / 2); ctx.lineTo(W, H / 2); ctx.stroke();

  if (analyser && audioCtx && audioCtx.state === 'running') {
    analyser.getByteTimeDomainData(wfDataArray);

    // Main waveform
    ctx.lineWidth = 2 * (window.devicePixelRatio || 1);
    ctx.strokeStyle = '#4cc9f0';
    ctx.beginPath();
    const bufLen = analyser.frequencyBinCount;
    const sliceW = W / bufLen;
    let x = 0;
    for (let i = 0; i < bufLen; i++) {
      const v = wfDataArray[i] / 128.0;
      const y = (v * H) / 2;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
      x += sliceW;
    }
    ctx.lineTo(W, H / 2);
    ctx.stroke();

    // Glow effect
    ctx.lineWidth = 6 * (window.devicePixelRatio || 1);
    ctx.strokeStyle = 'rgba(76,201,240,.08)';
    ctx.beginPath();
    x = 0;
    for (let i = 0; i < bufLen; i++) {
      const v = wfDataArray[i] / 128.0;
      const y = (v * H) / 2;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
      x += sliceW;
    }
    ctx.lineTo(W, H / 2);
    ctx.stroke();

    // Update info
    document.getElementById('wfSampleRate').textContent = audioCtx.sampleRate + ' Hz';
  } else if (!analyser) {
    // Draw flat line when no audio context yet
    ctx.lineWidth = 2 * (window.devicePixelRatio || 1);
    ctx.strokeStyle = 'rgba(76,201,240,.3)';
    ctx.beginPath();
    ctx.moveTo(0, H / 2);
    ctx.lineTo(W, H / 2);
    ctx.stroke();
  }

  wfAnimId = requestAnimationFrame(drawWaveform);
}

// Handle window resize
window.addEventListener('resize', () => {
  if (document.getElementById('panelWaveform').classList.contains('active')) {
    resizeCanvas();
  }
});

function ensureAudioCtx() {
  if (!audioCtx) {
    try {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)({sampleRate: 48000});
      gainNode = audioCtx.createGain();
      gainNode.gain.value = muted ? 0 : volume;
      // Create analyser for waveform visualization
      analyser = audioCtx.createAnalyser();
      analyser.fftSize = 2048;
      analyser.smoothingTimeConstant = 0.85;
      wfDataArray = new Uint8Array(analyser.frequencyBinCount);
      // Chain: source -> gainNode -> analyser -> destination
      gainNode.connect(analyser);
      analyser.connect(audioCtx.destination);
      console.log('[Audio] AudioContext created, state:', audioCtx.state, 'sampleRate:', audioCtx.sampleRate);
      startWaveform();
    } catch(e) {
      console.error('[Audio] AudioContext creation failed:', e);
      return false;
    }
  }
  // Resume if suspended (browser autoplay policy)
  if (audioCtx.state === 'suspended') {
    audioCtx.resume().then(() => {
      console.log('[Audio] AudioContext resumed');
      document.getElementById('audioStatus').textContent = '● Connected — Audio active';
      // Kick playback if queue has items
      if (audioQueue.length && !audioPlaying) playNext();
    });
  }
  return audioCtx.state === 'running';
}

function playNext() {
  if (!audioQueue.length) { audioPlaying = false; return; }
  if (!ensureAudioCtx()) {
    // AudioContext not ready yet (suspended) — wait for user gesture
    audioPlaying = false;
    document.getElementById('audioStatus').textContent = '● Connected — Click 🔊 to start audio';
    document.getElementById('audioStatus').className = 'status connected';
    console.log('[Audio] AudioContext suspended, waiting for user gesture. Queue:', audioQueue.length);
    return;
  }
  audioPlaying = true;

  const wav = audioQueue.shift();
  document.getElementById('infoQueue').textContent = audioQueue.length;
  console.log('[Audio] decoding segment, size:', wav.byteLength);

  try {
    audioCtx.decodeAudioData(wav.slice(0), d => {
      console.log('[Audio] decoded OK, duration:', d.duration.toFixed(2) + 's, ch:', d.numberOfChannels, 'sr:', d.sampleRate);
      try {
        const s = audioCtx.createBufferSource();
        s.buffer = d;
        s.connect(gainNode);
        s.onended = () => {
          segmentsPlayed++;
          document.getElementById('infoSegments').textContent = segmentsPlayed;
          document.getElementById('segCounter').textContent = segmentsPlayed + ' segments played';
          document.getElementById('wfSegInfo').textContent = segmentsPlayed + ' segments played';
          playNext();
        };
        s.start(0);
        startWaveform();
        document.getElementById('wfSegInfo').textContent = 'Playing · ' + d.duration.toFixed(1) + 's · ' + d.numberOfChannels + 'ch';
        document.getElementById('audioStatus').textContent = '● Playing';
        document.getElementById('audioStatus').className = 'status connected';
      } catch(e) {
        console.error('[Audio] playback start failed:', e);
        audioPlaying = false;
        setTimeout(playNext, 100);
      }
    }, (err) => {
      console.error('[Audio] decodeAudioData FAILED:', err);
      audioPlaying = false;
      setTimeout(playNext, 50);
    });
  } catch(e) {
    console.error('[Audio] decodeAudioData threw:', e);
    audioPlaying = false;
    setTimeout(playNext, 50);
  }
}

function toggleMute() {
  muted = !muted;
  const btn = document.getElementById('playBtn');
  btn.textContent = muted ? '🔇' : '🔊';
  btn.className = 'play-btn' + (muted ? ' muted' : '');
  ensureAudioCtx();
  if (gainNode) gainNode.gain.value = muted ? 0 : volume;
  // If there are queued segments and nothing is playing, start playback
  if (!muted && audioQueue.length && !audioPlaying) {
    setTimeout(playNext, 100); // small delay to let AudioContext resume
  }
}

function setVolume(v) {
  volume = v / 100;
  if (gainNode && !muted) gainNode.gain.value = volume;
}

// ═══ Autoplay policy: resume AudioContext on any user gesture ═══
document.addEventListener('click', function resumeAudio() {
  if (audioCtx && audioCtx.state === 'suspended') {
    audioCtx.resume().then(() => {
      console.log('[Audio] AudioContext resumed via user gesture');
      if (audioQueue.length && !audioPlaying) playNext();
    });
  }
  // Only need this once
  document.removeEventListener('click', resumeAudio);
}, {once: true});

// ═══ Show conditional rows ═══
if ('{{STATION_CATEGORY}}') document.getElementById('rowCategory').style.display = '';
if ('{{STATION_HOST}}') document.getElementById('rowHost').style.display = '';

// ═══ Init ═══
pollStatus();
refreshLog();
connectAudio();
resizeCanvas();
setInterval(pollStatus, 5000);
setInterval(refreshLog, 3000);
</script>
</body>
</html>"""


# ═══════════════════════════════════════════════════════════════════════════
# Server launcher
# ═══════════════════════════════════════════════════════════════════════════

def _get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def start_web_shell(port: int = WEB_SHELL_PORT, host: str = "0.0.0.0",
                    stop_event: Optional[threading.Event] = None,
                    callback_on_start: Optional[callable] = None):
    """
    Start the Radio OS web shell server.
    Can run standalone or in a daemon thread from shell_bookmark.py.
    """
    _ensure_imports()
    import uvicorn

    station_mgr = StationManager()
    audio_bridge = AudioBridge()
    app = create_shell_app(station_mgr, audio_bridge)

    local_ip = _get_local_ip()

    print(f"╔══════════════════════════════════════════════════╗")
    print(f"║  📻 Radio OS Web Shell                          ║")
    print(f"║  Local:     http://127.0.0.1:{port}               ║")
    print(f"║  Network:   http://{local_ip}:{port}{''.ljust(max(0, 17 - len(local_ip)))}║")
    print(f"║  Tailscale: Use your Tailscale IP + :{port}       ║")
    print(f"╚══════════════════════════════════════════════════╝")

    if callback_on_start:
        callback_on_start(f"http://{local_ip}:{port}")

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)

    if stop_event:
        def _watch():
            stop_event.wait()
            server.should_exit = True
            station_mgr.stop_all()
        threading.Thread(target=_watch, daemon=True).start()

    # Register cleanup on exit (only works from main thread)
    def _cleanup(*args):
        station_mgr.stop_all()
        server.should_exit = True

    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGINT, _cleanup)
        signal.signal(signal.SIGTERM, _cleanup)

    server.run()

    # Cleanup on exit
    station_mgr.stop_all()
    print("[Radio OS Web Shell] Server stopped.")


# ═══════════════════════════════════════════════════════════════════════════
# Standalone entry point
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Radio OS Web Shell Server")
    parser.add_argument("--port", type=int, default=WEB_SHELL_PORT, help=f"Port (default {WEB_SHELL_PORT})")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address")
    args = parser.parse_args()
    start_web_shell(port=args.port, host=args.host)
