#!/usr/bin/env python3
"""
puck_manager.py — ESP32 audio puck registry and audio router.

Manages up to 4 ESP32 audio pucks:
  - Tracks connected WebSocket clients keyed by node_id
  - Stores per-puck state: volume (0–100), mute, route
  - Routes outgoing PCM audio to one/all pucks
  - Exposes the /audio WebSocket endpoint for ESP32 connections
  - Exposes REST state / control used by web_server.py and audio_cli.py

Audio flow:
  Station TTS audio (WAV from .audio_pipe/)
      → PuckManager.broadcast_wav(wav_bytes, route)
          → resample to 16kHz PCM16 mono
          → apply volume scaling
          → send binary to matching connected pucks via WebSocket

Mic audio flow (future):
  ESP32 → /audio WS → PuckManager.on_mic_frame(node_id, pcm_bytes)
      → available via PuckManager.get_mic_stream(node_id)
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import struct
import time
import wave
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

# ─── Puck state ──────────────────────────────────────────────────────────────

ROUTE_ALL    = "all"      # broadcast to every connected puck
ROUTE_NONE   = "none"     # silence (no pucks)

@dataclass
class PuckState:
    node_id: int                         # 1–4
    volume: int = 80                     # 0–100
    muted: bool = False
    route: str = ROUTE_ALL               # "all" | "none" | "1,2" etc
    connected: bool = False
    connected_at: Optional[float] = None
    last_seen: Optional[float] = None
    ip: str = ""
    ws: Any = None                       # FastAPI WebSocket handle


# ─── PuckManager ─────────────────────────────────────────────────────────────

class PuckManager:
    """
    Singleton audio puck manager.  Instantiate once, attach to web_server app.
    """

    def __init__(self):
        self._pucks: Dict[int, PuckState] = {
            i: PuckState(node_id=i) for i in range(1, 5)
        }
        self._group_volume: int = 80      # 0–100, applied on top of per-puck
        self._lock = asyncio.Lock()

        # Mic frame callbacks: node_id → list of async callables
        self._mic_callbacks: Dict[int, List[Any]] = {i: [] for i in range(1, 5)}

        # Background poller task handle
        self._poller_task: Optional[Any] = None

    # ── Background audio poller ──────────────────────────────────────────────

    def start_poller(self, stations_dir: str):
        """Start the background task that polls station audio pipes.
        Call this once after the event loop is running (e.g. from a FastAPI
        startup event). Runs independently of any browser WebSocket connection.
        """
        if self._poller_task is not None:
            return
        self._poller_task = asyncio.ensure_future(
            self._poll_loop(stations_dir)
        )
        print("[PuckManager] Background audio poller started.", flush=True)

    async def _poll_loop(self, stations_dir: str):
        """Continuously scan all station audio pipes and broadcast to pucks."""
        while True:
            try:
                await self._poll_once(stations_dir)
            except Exception as e:
                print(f"[PuckManager] Poller error: {e}", flush=True)
            await asyncio.sleep(0.3)

    async def _poll_once(self, stations_dir: str):
        """Scan every station's .audio_pipe dir and broadcast new WAV files."""
        if not os.path.isdir(stations_dir):
            return
        # Check any connected pucks exist before doing file I/O
        if not any(p.connected for p in self._pucks.values()):
            return
        try:
            station_ids = os.listdir(stations_dir)
        except Exception:
            return
        for station_id in station_ids:
            audio_dir = os.path.join(stations_dir, station_id, ".audio_pipe")
            if not os.path.isdir(audio_dir):
                continue
            try:
                files = sorted(f for f in os.listdir(audio_dir) if f.endswith(".wav"))
            except Exception:
                continue
            for fname in files:
                fpath = os.path.join(audio_dir, fname)
                meta_path = fpath + ".json"
                try:
                    if time.time() - os.path.getmtime(fpath) < 0.2:
                        continue  # still being written
                except Exception:
                    continue
                try:
                    with open(fpath, "rb") as f:
                        wav_bytes = f.read()
                    if len(wav_bytes) < 44:
                        continue
                except Exception:
                    continue
                # Delete before broadcasting so we don't double-send
                try:
                    os.remove(fpath)
                    if os.path.exists(meta_path):
                        os.remove(meta_path)
                except Exception:
                    pass
                await self.broadcast_wav(wav_bytes, station_id=station_id)

    # ── State accessors ──────────────────────────────────────────────────────

    def get_all_state(self) -> Dict:
        return {
            "group_volume": self._group_volume,
            "pucks": {
                str(p.node_id): {
                    "node_id": p.node_id,
                    "connected": p.connected,
                    "volume": p.volume,
                    "muted": p.muted,
                    "route": p.route,
                    "ip": p.ip,
                    "last_seen": p.last_seen,
                }
                for p in self._pucks.values()
            }
        }

    def get_puck(self, node_id: int) -> Optional[PuckState]:
        return self._pucks.get(node_id)

    # ── Volume / mute / route control ────────────────────────────────────────

    def set_puck_volume(self, node_id: int, volume: int):
        """Set individual puck volume 0–100."""
        volume = max(0, min(100, volume))
        if node_id in self._pucks:
            self._pucks[node_id].volume = volume

    def set_group_volume(self, volume: int):
        """Set group volume 0–100 (multiplied with per-puck)."""
        self._group_volume = max(0, min(100, volume))

    def set_puck_mute(self, node_id: int, muted: bool):
        if node_id in self._pucks:
            self._pucks[node_id].muted = muted

    def mute_all(self, muted: bool):
        for p in self._pucks.values():
            p.muted = muted

    def set_puck_route(self, node_id: int, route: str):
        """
        Set which audio source this puck receives.
        route: "all" | "none" | station_id string
        """
        if node_id in self._pucks:
            self._pucks[node_id].route = route

    def set_all_route(self, route: str):
        for p in self._pucks.values():
            p.route = route

    # ── WebSocket connection management ──────────────────────────────────────

    async def on_puck_connect(self, ws: Any, node_id: int, ip: str = ""):
        """Called when an ESP32 puck WebSocket connects and sends HELLO."""
        async with self._lock:
            p = self._pucks.get(node_id)
            if p is None:
                return
            p.ws = ws
            p.connected = True
            p.connected_at = time.time()
            p.last_seen = time.time()
            p.ip = ip
        print(f"[PuckManager] Puck {node_id} connected  ip={ip}", flush=True)

    async def on_puck_disconnect(self, node_id: int):
        async with self._lock:
            p = self._pucks.get(node_id)
            if p:
                p.ws = None
                p.connected = False
        print(f"[PuckManager] Puck {node_id} disconnected", flush=True)

    async def on_puck_heartbeat(self, node_id: int):
        async with self._lock:
            p = self._pucks.get(node_id)
            if p:
                p.last_seen = time.time()

    # ── Mic audio ingestion ───────────────────────────────────────────────────

    async def on_mic_frame(self, node_id: int, pcm_bytes: bytes):
        """Called with raw 16-bit PCM frames from a puck's mic."""
        p = self._pucks.get(node_id)
        if p:
            p.last_seen = time.time()
        for cb in self._mic_callbacks.get(node_id, []):
            try:
                await cb(node_id, pcm_bytes)
            except Exception as e:
                print(f"[PuckManager] Mic callback error node={node_id}: {e}", flush=True)

    def register_mic_callback(self, node_id: int, cb):
        """Register an async callback(node_id, pcm_bytes) for mic frames."""
        self._mic_callbacks.setdefault(node_id, []).append(cb)

    # ── Audio broadcast ───────────────────────────────────────────────────────

    async def broadcast_wav(self, wav_bytes: bytes, station_id: str = ""):
        """
        Convert WAV bytes to 16kHz PCM16 mono, apply volume, send to pucks
        whose route matches station_id (or route == "all").
        """
        try:
            pcm = _wav_to_pcm16_mono_16k(wav_bytes)
        except Exception as e:
            print(f"[PuckManager] WAV decode failed: {e}", flush=True)
            return

        tasks = []
        for p in self._pucks.values():
            if not p.connected or p.ws is None:
                continue
            if p.muted:
                continue
            if p.route == ROUTE_NONE:
                continue
            if p.route != ROUTE_ALL and station_id and station_id not in p.route.split(","):
                continue
            # Apply combined volume
            eff_vol = (p.volume / 100.0) * (self._group_volume / 100.0)
            out = _scale_pcm16(pcm, eff_vol) if eff_vol < 0.99 else pcm
            tasks.append(_send_to_puck(p, out))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def send_to_puck(self, node_id: int, pcm_bytes: bytes):
        """Send raw PCM bytes directly to one puck (for testing)."""
        p = self._pucks.get(node_id)
        if p and p.connected and p.ws and not p.muted:
            eff_vol = (p.volume / 100.0) * (self._group_volume / 100.0)
            out = _scale_pcm16(pcm_bytes, eff_vol) if eff_vol < 0.99 else pcm_bytes
            await _send_to_puck(p, out)

    async def send_test_tone(self, node_id: int, freq_hz: int = 440, duration_ms: int = 500):
        """Send a sine-wave test tone to a specific puck."""
        import math
        sample_rate = 16000
        n = int(sample_rate * duration_ms / 1000)
        samples = [
            int(32767 * 0.5 * math.sin(2 * math.pi * freq_hz * i / sample_rate))
            for i in range(n)
        ]
        pcm = struct.pack(f"<{n}h", *samples)
        await self.send_to_puck(node_id, pcm)


# ── Helper: FastAPI WebSocket handler ────────────────────────────────────────

async def handle_puck_websocket(ws: Any, puck_mgr: "PuckManager"):
    """
    FastAPI WebSocket handler for /audio.
    Called by web_server.py's @app.websocket("/audio") route.

    Protocol:
      ESP32 → text  "HELLO:node<N>"   — identify self
      ESP32 → text  "PING"            — keepalive
      ESP32 → bytes <pcm>             — mic audio frame
      Server → bytes <pcm>            — speaker audio frame
    """
    await ws.accept()
    node_id: Optional[int] = None
    client_ip = ""

    try:
        client_ip = ws.client.host if ws.client else ""
    except Exception:
        pass

    print(f"[PuckWS] New connection from {client_ip}", flush=True)

    try:
        while True:
            msg = await asyncio.wait_for(ws.receive(), timeout=30.0)
            if msg["type"] == "websocket.disconnect":
                break

            if "text" in msg and msg["text"]:
                text = msg["text"].strip()
                if text.startswith("HELLO:node"):
                    try:
                        node_id = int(text.split("node")[1])
                        await puck_mgr.on_puck_connect(ws, node_id, client_ip)
                        await ws.send_text(f"ACK:node{node_id}")
                    except Exception as e:
                        print(f"[PuckWS] Bad HELLO: {text}  err={e}", flush=True)
                elif text == "PING":
                    if node_id:
                        await puck_mgr.on_puck_heartbeat(node_id)
                    try:
                        await ws.send_text("PONG")
                    except Exception:
                        break

            elif "bytes" in msg and msg["bytes"] and node_id:
                await puck_mgr.on_mic_frame(node_id, msg["bytes"])

    except asyncio.TimeoutError:
        print(f"[PuckWS] node={node_id} timed out", flush=True)
    except Exception as e:
        print(f"[PuckWS] node={node_id} error: {e}", flush=True)
    finally:
        if node_id:
            await puck_mgr.on_puck_disconnect(node_id)
        try:
            await ws.close()
        except Exception:
            pass


# ── DSP helpers ───────────────────────────────────────────────────────────────

def _wav_to_pcm16_mono_16k(wav_bytes: bytes) -> bytes:
    """Read WAV bytes, return raw 16-bit mono PCM at 16kHz."""
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        n_channels = wf.getnchannels()
        sampwidth  = wf.getsampwidth()
        framerate  = wf.getframerate()
        n_frames   = wf.getnframes()
        raw = wf.readframes(n_frames)

    # Convert to 16-bit signed if needed
    if sampwidth == 1:
        # 8-bit unsigned → 16-bit signed
        samples = struct.unpack(f"{len(raw)}B", raw)
        raw = struct.pack(f"<{len(samples)}h", *[(s - 128) * 256 for s in samples])
        sampwidth = 2
    elif sampwidth == 4:
        samples = struct.unpack(f"<{len(raw)//4}i", raw)
        raw = struct.pack(f"<{len(samples)}h", *[s >> 16 for s in samples])
        sampwidth = 2

    # Mix to mono
    if n_channels > 1:
        n = len(raw) // (sampwidth * n_channels)
        mixed = []
        for i in range(n):
            chans = struct.unpack_from(f"<{n_channels}h", raw, i * sampwidth * n_channels)
            mixed.append(sum(chans) // n_channels)
        raw = struct.pack(f"<{len(mixed)}h", *mixed)

    # Resample to 16kHz (simple integer ratio or linear interpolation)
    if framerate != 16000:
        raw = _resample_pcm16(raw, framerate, 16000)

    return raw


def _resample_pcm16(data: bytes, src_rate: int, dst_rate: int) -> bytes:
    """Simple linear interpolation resample for PCM16 mono."""
    if src_rate == dst_rate:
        return data
    n_src = len(data) // 2
    samples_src = struct.unpack(f"<{n_src}h", data)
    ratio = src_rate / dst_rate
    n_dst = int(n_src / ratio)
    out = []
    for i in range(n_dst):
        pos = i * ratio
        lo  = int(pos)
        hi  = min(lo + 1, n_src - 1)
        frac = pos - lo
        val = int(samples_src[lo] * (1 - frac) + samples_src[hi] * frac)
        out.append(max(-32768, min(32767, val)))
    return struct.pack(f"<{n_dst}h", *out)


def _scale_pcm16(data: bytes, scale: float) -> bytes:
    """Scale PCM16 amplitude by a factor 0.0–1.0."""
    n = len(data) // 2
    samples = struct.unpack(f"<{n}h", data)
    scaled = [max(-32768, min(32767, int(s * scale))) for s in samples]
    return struct.pack(f"<{n}h", *scaled)


async def _send_to_puck(p: PuckState, pcm: bytes):
    try:
        await p.ws.send_bytes(pcm)
    except Exception as e:
        print(f"[PuckManager] Send to puck {p.node_id} failed: {e}", flush=True)
        p.connected = False
        p.ws = None


# ── Module-level singleton ────────────────────────────────────────────────────
_instance: Optional[PuckManager] = None

def get_puck_manager() -> PuckManager:
    global _instance
    if _instance is None:
        _instance = PuckManager()
    return _instance
