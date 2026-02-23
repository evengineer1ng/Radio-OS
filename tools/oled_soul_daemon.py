#!/usr/bin/env python3
"""
Transparent OLED "Soul Display" daemon — v2 State Machine Edition.

Renders deterministic motion glyphs on a 128x64 OLED reacting to UDP JSON
events from the RadioOS runtime.

Architecture
────────────
  Tier 0 — Power/System state  (OFF · BOOTING · IDLE · ACTIVE · MUTED · ERROR)
  Tier 1 — Interaction mode    (HOME · STATION_SELECTED · SIMULATION · LISTENING
                                SPEAKING · PROCESSING)
  Tier 2 — Station personality (FTB · ORACLE · HOCKEY · AMBIENT)

Rendered frame = base_motion(T0) + interaction_pulse(T1) + station_motif(T2)

Motion design rules
───────────────────
  • 0.1–0.5 Hz slow drift baseline
  • 1–2 Hz interaction pulses
  • Bezier (ease-in-out / ease-out-cubic) easing — never linear transitions
  • Max perceived 4–6 Hz  — no jitter, no toy-speed flicker
  • State transitions morph — they never cut

Plugin motion-profile contract
───────────────────────────────
  Meta-plugins may expose an ``OLED_MOTION_PROFILE`` dict:
      {
        "motion_profile": "orbital" | "radial" | "fracture" | "linear",
        "intensity": 0.0 – 1.0,
        "color_palette": [...]   # reserved for future colour OLED support
      }
  The scheduler picks it up via the ``station_id`` field in event payloads.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import socket
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple
from collections import deque

try:
    from PIL import Image, ImageDraw
    HAS_PIL = True
except Exception:
    Image = Any  # type: ignore
    ImageDraw = Any  # type: ignore
    HAS_PIL = False

try:
    from tools.oled_event_client import DEFAULT_UDP_HOST, DEFAULT_UDP_PORT, send_oled_event
except Exception:
    from oled_event_client import DEFAULT_UDP_HOST, DEFAULT_UDP_PORT, send_oled_event  # type: ignore

try:
    from luma.core.interface.serial import spi  # type: ignore
    from luma.oled import device as oled_device  # type: ignore
    HAS_LUMA = True
except Exception:
    HAS_LUMA = False


# ---------------------------------------------------------------------------
# Math helpers
# ---------------------------------------------------------------------------


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def ease_in_out(t: float) -> float:
    t = clamp(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def ease_out_cubic(t: float) -> float:
    t = clamp(t, 0.0, 1.0)
    return 1.0 - pow(1.0 - t, 3.0)


def triangle_wave(t: float) -> float:
    """t in [0..1] -> triangle wave in [0..1]."""
    t = t % 1.0
    if t < 0.5:
        return t * 2.0
    return (1.0 - t) * 2.0


# ---------------------------------------------------------------------------
# Drawing primitives
# ---------------------------------------------------------------------------


def draw_ring(
    draw: ImageDraw.ImageDraw,
    cx: float,
    cy: float,
    radius: float,
    brightness: int = 255,
    width: int = 1,
) -> None:
    if radius <= 0:
        return
    b = int(clamp(brightness, 0, 255))
    for w in range(max(1, width)):
        r = radius + w
        box = (cx - r, cy - r, cx + r, cy + r)
        draw.ellipse(box, outline=b)


def draw_arc(
    draw: ImageDraw.ImageDraw,
    cx: float,
    cy: float,
    radius: float,
    start_deg: float,
    end_deg: float,
    brightness: int = 255,
    width: int = 1,
) -> None:
    if radius <= 0:
        return
    b = int(clamp(brightness, 0, 255))
    box = (cx - radius, cy - radius, cx + radius, cy + radius)
    draw.arc(box, start=start_deg, end=end_deg, fill=b, width=max(1, width))


def draw_spark(draw: ImageDraw.ImageDraw, x: float, y: float, brightness: int = 255, size: int = 1) -> None:
    b = int(clamp(brightness, 0, 255))
    if size <= 1:
        draw.point((x, y), fill=b)
        return
    draw.line((x - size, y, x + size, y), fill=b, width=1)
    draw.line((x, y - size, x, y + size), fill=b, width=1)


def draw_shard(
    draw: ImageDraw.ImageDraw,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    brightness: int = 255,
    width: int = 1,
) -> None:
    b = int(clamp(brightness, 0, 255))
    draw.line((x1, y1, x2, y2), fill=b, width=max(1, width))


def draw_wave(
    draw: ImageDraw.ImageDraw,
    width: int,
    height: int,
    center_y: float,
    amplitude: float,
    phase: float,
    tilt: float,
    brightness: int = 255,
) -> None:
    b = int(clamp(brightness, 0, 255))
    points: List[Tuple[float, float]] = []
    for x in range(width):
        nx = x / max(1, width - 1)
        y = center_y + math.sin((nx * math.tau * 2.0) + phase) * amplitude
        y += tilt * ((nx - 0.5) * 18.0)
        points.append((x, y))
    if len(points) > 1:
        draw.line(points, fill=b, width=1)


def polar_point(cx: float, cy: float, radius: float, angle_rad: float) -> Tuple[float, float]:
    return (cx + math.cos(angle_rad) * radius, cy + math.sin(angle_rad) * radius)


# ---------------------------------------------------------------------------
# Animation base
# ---------------------------------------------------------------------------


class Animation:
    duration_ms: int = 1000
    priority: int = 0
    loop: bool = False

    def __init__(self) -> None:
        self.started_ms: int = 0

    def start(self, now_ms: int) -> None:
        self.started_ms = now_ms

    def elapsed_ms(self, now_ms: int) -> int:
        return max(0, now_ms - self.started_ms)

    def progress(self, now_ms: int) -> float:
        if self.duration_ms <= 0:
            return 1.0
        if self.loop:
            return (self.elapsed_ms(now_ms) % self.duration_ms) / float(self.duration_ms)
        return clamp(self.elapsed_ms(now_ms) / float(self.duration_ms), 0.0, 1.0)

    def done(self, now_ms: int) -> bool:
        if self.loop:
            return False
        return self.elapsed_ms(now_ms) >= self.duration_ms

    def render(self, draw: ImageDraw.ImageDraw, now_ms: int, width: int, height: int) -> None:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# State loops
# ---------------------------------------------------------------------------


class BreathingHaloLoop(Animation):
    duration_ms = 14000
    priority = 0
    loop = True

    def __init__(self, rng: random.Random) -> None:
        super().__init__()
        self._stars = []
        for _ in range(12):
            self._stars.append(
                {
                    "angle": rng.uniform(0.0, math.tau),
                    "speed": rng.uniform(0.015, 0.045),
                    "offset": rng.random(),
                    "size": 1 if rng.random() < 0.75 else 2,
                }
            )

    def render(self, draw: ImageDraw.ImageDraw, now_ms: int, width: int, height: int) -> None:
        t = self.progress(now_ms)
        cx, cy = width / 2.0, height / 2.0

        breath = 0.5 + 0.5 * math.sin(t * math.tau)
        radius = lerp(10.0, 14.0, breath)
        draw_ring(draw, cx, cy, radius, brightness=220, width=1)
        draw_arc(draw, cx, cy, radius + 2.0, 210, 300, brightness=110, width=1)

        seconds = now_ms / 1000.0
        for star in self._stars:
            phase = ((seconds * star["speed"]) + star["offset"]) % 1.0
            r = 4.0 + phase * 26.0
            fade = 1.0 - phase
            x, y = polar_point(cx, cy, r, star["angle"])
            if 0 <= x < width and 0 <= y < height:
                draw_spark(draw, x, y, brightness=int(90 * fade), size=star["size"])


class OrbitCalmLoop(Animation):
    duration_ms = 10000
    priority = 0
    loop = True

    def render(self, draw: ImageDraw.ImageDraw, now_ms: int, width: int, height: int) -> None:
        t = self.progress(now_ms)
        cx, cy = width / 2.0, height / 2.0

        collapse = triangle_wave((t * 0.5) % 1.0) * 0.30
        base_r = 13.0 * (1.0 - collapse)
        draw_ring(draw, cx, cy, 10.0 + math.sin(t * math.tau) * 0.8, brightness=90, width=1)

        for idx, speed in enumerate((1.0, 0.72, 1.28)):
            angle = (t * math.tau * speed) + (idx * (math.tau / 3.0))
            r = base_r + (idx - 1) * 2.0
            x, y = polar_point(cx, cy, r, angle)
            draw_spark(draw, x, y, brightness=210, size=1)


class ListeningLoop(Animation):
    duration_ms = 2200
    priority = 3
    loop = True

    def render(self, draw: ImageDraw.ImageDraw, now_ms: int, width: int, height: int) -> None:
        t = self.progress(now_ms)
        cx, cy = width / 2.0, height / 2.0

        base_r = 12.0
        draw_ring(draw, cx, cy, base_r, brightness=150, width=1)
        arc_len = 90.0
        start = (t * 360.0) % 360.0
        draw_arc(draw, cx, cy, base_r + 1.0, start, start + arc_len, brightness=255, width=2)

        ripple_t = triangle_wave((t * 1.5) % 1.0)
        ripple_r = base_r + ripple_t * 10.0
        ripple_b = int((1.0 - ripple_t) * 80.0)
        draw_ring(draw, cx, cy, ripple_r, brightness=ripple_b, width=1)


class ThinkingLoop(Animation):
    duration_ms = 3000
    priority = 2
    loop = True

    def render(self, draw: ImageDraw.ImageDraw, now_ms: int, width: int, height: int) -> None:
        t = self.progress(now_ms)
        seconds = now_ms / 1000.0
        cx, cy = width / 2.0, height / 2.0

        angles: List[float] = []
        for idx, speed in enumerate((0.82, 1.17, 1.43)):
            a = (seconds * speed * math.tau) + idx * (math.tau / 3.0)
            angles.append(a)
            r = 8.0 + idx * 3.0
            x, y = polar_point(cx, cy, r, a)
            draw_spark(draw, x, y, brightness=220, size=1)

        align_score = (
            abs(math.sin(angles[0] - angles[1]))
            + abs(math.sin(angles[1] - angles[2]))
            + abs(math.sin(angles[2] - angles[0]))
        )
        flash = clamp(1.0 - (align_score / 1.2), 0.0, 1.0)
        if flash > 0.0:
            draw_ring(draw, cx, cy, 5.0 + flash * 4.0, brightness=int(80 + flash * 140), width=1)

        spark_phase = triangle_wave((t * 2.0) % 1.0)
        if spark_phase > 0.70:
            draw_spark(draw, cx + math.sin(seconds * 4.0) * 2.5, cy + math.cos(seconds * 3.3) * 2.0, brightness=190, size=1)


class ErrorLoop(Animation):
    duration_ms = 2600
    priority = 4
    loop = True

    def render(self, draw: ImageDraw.ImageDraw, now_ms: int, width: int, height: int) -> None:
        t = self.progress(now_ms)
        cx, cy = width / 2.0, height / 2.0

        blink = 0.35 + 0.65 * triangle_wave(t)
        draw_ring(draw, cx, cy, 11.0, brightness=int(70 * blink), width=1)

        base = [
            (-12, -6, -3, -1),
            (12, -6, 3, -1),
            (-10, 8, -1, 2),
            (10, 8, 2, 3),
        ]
        jitter = math.sin(t * math.tau * 5.0) * 1.2
        for x1, y1, x2, y2 in base:
            draw_shard(
                draw,
                cx + x1 + jitter,
                cy + y1 - jitter,
                cx + x2 + jitter,
                cy + y2 - jitter,
                brightness=int(120 + 80 * blink),
                width=1,
            )


# ---------------------------------------------------------------------------
# Ritual animations
# ---------------------------------------------------------------------------


class BootIgnition(Animation):
    duration_ms = 900
    priority = 4

    def render(self, draw: ImageDraw.ImageDraw, now_ms: int, width: int, height: int) -> None:
        t = self.progress(now_ms)
        cx, cy = width / 2.0, height / 2.0

        if t < 0.10:
            draw_spark(draw, cx, cy, brightness=255, size=2)
            return

        if t < 0.45:
            p = ease_out_cubic((t - 0.10) / 0.35)
            draw_ring(draw, cx, cy, lerp(1.0, 15.5, p), brightness=255, width=1)
            return

        p = (t - 0.45) / 0.55
        pulse = math.sin(p * math.tau * 2.0) * 1.4
        radius = 13.0 + pulse
        draw_ring(draw, cx, cy, radius, brightness=230, width=2)
        draw_arc(draw, cx, cy, radius + 2.0, 230, 320, brightness=140, width=1)


class PortalOpen(Animation):
    duration_ms = 850
    priority = 2

    def render(self, draw: ImageDraw.ImageDraw, now_ms: int, width: int, height: int) -> None:
        t = self.progress(now_ms)
        cx, cy = width / 2.0, height / 2.0

        if t < 0.60:
            p = ease_out_cubic(t / 0.60)
            r = lerp(8.0, 26.0, p)
        else:
            p = ease_in_out((t - 0.60) / 0.40)
            r = lerp(26.0, 13.0, p)
        draw_ring(draw, cx, cy, r, brightness=230, width=1)

        spin = lerp(0.0, math.radians(20.0), ease_in_out(clamp(t / 0.80, 0.0, 1.0)))
        for a in (0.0, math.pi / 2.0, math.pi, 3.0 * math.pi / 2.0):
            p1 = polar_point(cx, cy, 17.0, a + spin)
            p2 = polar_point(cx, cy, 22.0, a + spin)
            draw_shard(draw, p1[0], p1[1], p2[0], p2[1], brightness=190, width=1)


class PortalClose(Animation):
    duration_ms = 760
    priority = 2

    def __init__(self, rng: random.Random) -> None:
        super().__init__()
        self._dots = []
        for _ in range(8):
            self._dots.append(
                {
                    "angle": rng.uniform(0.0, math.tau),
                    "radius": rng.uniform(16.0, 28.0),
                }
            )

    def render(self, draw: ImageDraw.ImageDraw, now_ms: int, width: int, height: int) -> None:
        t = self.progress(now_ms)
        cx, cy = width / 2.0, height / 2.0

        r = lerp(14.0, 0.0, ease_in_out(t))
        draw_ring(draw, cx, cy, max(0.0, r), brightness=180, width=1)

        for dot in self._dots:
            dr = lerp(dot["radius"], 1.0, ease_out_cubic(t))
            x, y = polar_point(cx, cy, dr, dot["angle"])
            draw_spark(draw, x, y, brightness=int(160 * (1.0 - t)), size=1)

        if t > 0.72:
            pulse = (t - 0.72) / 0.28
            draw_ring(draw, cx, cy, 2.0 + pulse * 6.0, brightness=int(120 * (1.0 - pulse)), width=1)


class ScanLock(Animation):
    duration_ms = 1100
    priority = 1

    def render(self, draw: ImageDraw.ImageDraw, now_ms: int, width: int, height: int) -> None:
        t = self.progress(now_ms)
        cx, cy = width / 2.0, height / 2.0

        draw_ring(draw, cx, cy, 11.5, brightness=90, width=1)
        draw_ring(draw, cx, cy, 16.0, brightness=40, width=1)

        if t < 0.50:
            x = lerp(0.0, width - 1.0, t / 0.50)
        else:
            x = lerp(0.0, width - 1.0, (t - 0.50) / 0.50)
        draw.line((x, 8, x, height - 8), fill=180, width=1)

        if t > 0.86:
            p = (t - 0.86) / 0.14
            draw_ring(draw, cx, cy, 10.0 + p * 5.0, brightness=int(220 * (1.0 - p)), width=2)


class RipplesOn(Animation):
    duration_ms = 520
    priority = 3

    def render(self, draw: ImageDraw.ImageDraw, now_ms: int, width: int, height: int) -> None:
        t = self.progress(now_ms)
        cx, cy = width / 2.0, height / 2.0

        for idx, offset in enumerate((0.0, 0.18, 0.36)):
            pt = clamp((t - offset) / 0.64, 0.0, 1.0)
            if pt <= 0.0:
                continue
            r = lerp(4.0, 22.0, ease_out_cubic(pt))
            b = int(220 * (1.0 - pt))
            draw_ring(draw, cx, cy, r, brightness=b, width=1)
        draw_arc(draw, cx, cy, 13.0, t * 260.0, t * 260.0 + 70.0, brightness=220, width=2)


class DampenOff(Animation):
    duration_ms = 360
    priority = 3

    def render(self, draw: ImageDraw.ImageDraw, now_ms: int, width: int, height: int) -> None:
        t = self.progress(now_ms)
        cx, cy = width / 2.0, height / 2.0

        arc_r = lerp(13.0, 2.0, ease_in_out(t))
        span = lerp(90.0, 12.0, ease_in_out(t))
        start = lerp(220.0, 270.0, ease_in_out(t))
        draw_arc(draw, cx, cy, arc_r, start, start + span, brightness=int(220 * (1.0 - t * 0.7)), width=2)
        draw_spark(draw, cx, cy, brightness=int(200 * (1.0 - t)), size=1)


class ResolvePulse(Animation):
    duration_ms = 250
    priority = 2

    def render(self, draw: ImageDraw.ImageDraw, now_ms: int, width: int, height: int) -> None:
        t = self.progress(now_ms)
        cx, cy = width / 2.0, height / 2.0
        r = lerp(4.0, 18.0, ease_out_cubic(t))
        b = int(240 * (1.0 - t))
        draw_ring(draw, cx, cy, r, brightness=b, width=2 if t < 0.4 else 1)


class Fracture(Animation):
    duration_ms = 920
    priority = 5

    def render(self, draw: ImageDraw.ImageDraw, now_ms: int, width: int, height: int) -> None:
        t = self.progress(now_ms)
        cx, cy = width / 2.0, height / 2.0
        if t < 0.25:
            p = t / 0.25
            draw_ring(draw, cx, cy, lerp(2.0, 12.0, ease_out_cubic(p)), brightness=255, width=1)
            return

        p = (t - 0.25) / 0.75
        jitter = math.sin(p * math.tau * 6.0) * 1.8 * (1.0 - p)
        brightness = int(220 - p * 80)
        segments = [
            (-12, -5, -4, -1),
            (-3, -2, 2, 1),
            (2, 1, 8, 4),
            (11, -7, 4, -2),
            (-9, 8, -2, 2),
            (10, 8, 3, 2),
        ]
        for x1, y1, x2, y2 in segments:
            draw_shard(draw, cx + x1 + jitter, cy + y1 - jitter, cx + x2 + jitter, cy + y2 - jitter, brightness=brightness, width=1)


class VolumeTilt(Animation):
    duration_ms = 240
    priority = 1

    def __init__(self, direction: int, intensity: int = 1) -> None:
        super().__init__()
        self.direction = 1 if direction >= 0 else -1
        self.intensity = int(clamp(float(intensity), 1.0, 4.0))

    def render(self, draw: ImageDraw.ImageDraw, now_ms: int, width: int, height: int) -> None:
        t = self.progress(now_ms)
        cx, cy = width / 2.0, height / 2.0

        amp = lerp(2.0 + self.intensity, 0.8, t)
        tilt = self.direction * (1.0 - t)
        draw_wave(draw, width, height, cy, amp, phase=t * math.tau * 2.0, tilt=tilt, brightness=220)
        draw_ring(draw, cx, cy, 9.0 + amp * 0.4, brightness=90, width=1)


class SideWind(Animation):
    duration_ms = 200
    priority = 1

    def __init__(self, direction: int) -> None:
        super().__init__()
        self.direction = 1 if direction >= 0 else -1

    def render(self, draw: ImageDraw.ImageDraw, now_ms: int, width: int, height: int) -> None:
        t = self.progress(now_ms)
        cx, cy = width / 2.0, height / 2.0

        for idx in range(7):
            row = idx % 3
            y = 18 + row * 12 + ((idx // 3) * 2)
            start_x = -6 if self.direction > 0 else width + 6
            end_x = width + 6 if self.direction > 0 else -6
            x = lerp(start_x, end_x, t + idx * 0.04)
            if 0 <= x < width:
                draw_spark(draw, x, y, brightness=160, size=1)

        lean = self.direction * (1.0 - t) * 22.0
        draw_arc(draw, cx, cy, 12.0, 250.0 + lean, 320.0 + lean, brightness=210, width=2)


class Ping(Animation):
    duration_ms = 200
    priority = 1

    def render(self, draw: ImageDraw.ImageDraw, now_ms: int, width: int, height: int) -> None:
        t = self.progress(now_ms)
        cx, cy = width / 2.0, height / 2.0
        r = lerp(3.0, 12.0, ease_out_cubic(t))
        draw_ring(draw, cx, cy, r, brightness=int(240 * (1.0 - t)), width=1)


# ===========================================================================
# Tier 0 — Power / System state loops
# ===========================================================================


class FieldDriftLoop(Animation):
    """IDLE — layered organic motion: orbital arcs, drifting sparks, lazy
    constellation lines, and a slow-morphing ring breath.

    Four independently-timed layers keep things perpetually mutating without
    ever feeling frantic:
      L0  slow-breath ring  (0.07 Hz)       — barely-there heartbeat
      L1  orbital arc pack  (3–5 arcs, 0.05–0.14 rev/s) — parallax drift
      L2  constellation     (6 nodes, sub-Hz wander, connecting lines)
      L3  deep-field sparks (8 particles, very slow traverse)

    Every parameter is seeded from rng so two daemon restarts look different.
    """
    duration_ms = 28000
    priority = 0
    loop = True

    def __init__(self, rng: random.Random) -> None:
        super().__init__()

        # L0 — breath ring params
        self._breath_r_min = rng.uniform(8.0, 10.0)
        self._breath_r_max = rng.uniform(14.0, 18.0)
        self._breath_period = rng.uniform(11.0, 16.0)   # seconds per cycle
        self._breath_bright_base = rng.randint(28, 42)

        # L1 — orbital arcs
        self._arcs: List[Dict[str, float]] = []
        n_arcs = rng.randint(4, 6)
        for i in range(n_arcs):
            self._arcs.append({
                "radius":   8.0 + i * 3.8 + rng.uniform(-1.0, 1.0),
                "speed":    rng.uniform(0.042, 0.13),    # rev/s
                "phase":    rng.uniform(0.0, math.tau),
                "arc_base": rng.uniform(40.0, 90.0),     # deg — base arc length
                "arc_var":  rng.uniform(15.0, 40.0),     # deg — variation amplitude
                "arc_rate": rng.uniform(0.07, 0.22),     # Hz — how fast arc length morphs
                "bright":   rng.randint(38, 75),
            })

        # L2 — constellation: nodes wander slowly, draw lines between close pairs
        self._nodes: List[Dict[str, float]] = []
        for _ in range(6):
            # Anchor to a soft zone so nodes don't leave display edge
            ax = rng.uniform(0.18, 0.82)
            ay = rng.uniform(0.18, 0.82)
            self._nodes.append({
                "ax": ax, "ay": ay,
                "px": ax, "py": ay,
                "vx": rng.uniform(-0.0008, 0.0008),
                "vy": rng.uniform(-0.0006, 0.0006),
                "wander_r":  rng.uniform(0.06, 0.14),   # fraction of screen
                "wander_sp": rng.uniform(0.04, 0.10),   # Hz
                "wander_ph": rng.uniform(0.0, math.tau),
                "bright": rng.randint(22, 45),
            })
        self._connect_dist_sq = (0.28 * 128) ** 2   # px² — max connect distance

        # L3 — deep-field sparks
        self._sparks: List[Dict[str, float]] = []
        for _ in range(8):
            self._sparks.append({
                "x":   rng.uniform(0.0, 1.0),
                "y":   rng.uniform(0.0, 1.0),
                "vx":  rng.uniform(-0.0015, 0.0015),
                "vy":  rng.uniform(-0.0010, 0.0010),
                "bright": rng.randint(14, 30),
                "twinkle_rate": rng.uniform(0.08, 0.25),  # Hz
                "twinkle_ph":   rng.uniform(0.0, math.tau),
            })

    def render(self, draw: ImageDraw.ImageDraw, now_ms: int, width: int, height: int) -> None:
        seconds = now_ms / 1000.0
        cx, cy = width / 2.0, height / 2.0

        # ── L0: slow-breath ring ──────────────────────────────────────────
        breath_t = 0.5 + 0.5 * math.sin(seconds / self._breath_period * math.tau)
        breath_t = ease_in_out(breath_t)
        r_breath = lerp(self._breath_r_min, self._breath_r_max, breath_t)
        b_breath = int(self._breath_bright_base + 18 * breath_t)
        draw_ring(draw, cx, cy, r_breath, brightness=b_breath, width=1)

        # ── L1: orbital arcs ─────────────────────────────────────────────
        for arc in self._arcs:
            angle_rad = (seconds * arc["speed"] * math.tau) + arc["phase"]
            # Arc length morphs slowly → feels organic, never locked
            arc_len = arc["arc_base"] + arc["arc_var"] * math.sin(
                seconds * arc["arc_rate"] * math.tau
            )
            start_deg = math.degrees(angle_rad)
            draw_arc(draw, cx, cy, arc["radius"],
                     start_deg, start_deg + arc_len,
                     brightness=int(arc["bright"]), width=1)

        # ── L2: constellation nodes ───────────────────────────────────────
        pos: List[Tuple[float, float]] = []
        for nd in self._nodes:
            # Nodes orbit slowly around their anchor point
            wx = nd["ax"] + nd["wander_r"] * 0.5 * math.cos(
                seconds * nd["wander_sp"] * math.tau + nd["wander_ph"]
            )
            wy = nd["ay"] + nd["wander_r"] * 0.3 * math.sin(
                seconds * nd["wander_sp"] * math.tau + nd["wander_ph"] + 1.1
            )
            # Soft-clamp inside screen
            wx = clamp(wx, 0.05, 0.95)
            wy = clamp(wy, 0.05, 0.95)
            px, py = wx * width, wy * height
            pos.append((px, py))
            draw_spark(draw, px, py, brightness=nd["bright"], size=1)

        # Draw lines between close-enough node pairs
        for i in range(len(pos)):
            for j in range(i + 1, len(pos)):
                dx = pos[i][0] - pos[j][0]
                dy = pos[i][1] - pos[j][1]
                dist_sq = dx * dx + dy * dy
                if dist_sq < self._connect_dist_sq and dist_sq > 0:
                    # Fade line by distance
                    fade = 1.0 - (dist_sq / self._connect_dist_sq)
                    b_line = int(18 + 26 * fade * fade)
                    draw.line((pos[i][0], pos[i][1], pos[j][0], pos[j][1]),
                              fill=b_line, width=1)

        # ── L3: deep-field sparks (twinkle) ──────────────────────────────
        for sp in self._sparks:
            px = (sp["x"] + seconds * sp["vx"]) % 1.0
            py = (sp["y"] + seconds * sp["vy"]) % 1.0
            twinkle = 0.5 + 0.5 * math.sin(
                seconds * sp["twinkle_rate"] * math.tau + sp["twinkle_ph"]
            )
            b = int(sp["bright"] * twinkle)
            if b > 4:
                draw_spark(draw, px * width, py * height, brightness=b, size=1)


class MutedPulse(Animation):
    """MUTED — very slow, low-brightness single ring breath. Barely alive."""
    duration_ms = 8000
    priority = 0
    loop = True

    def render(self, draw: ImageDraw.ImageDraw, now_ms: int, width: int, height: int) -> None:
        t = self.progress(now_ms)
        cx, cy = width / 2.0, height / 2.0
        breath = 0.5 + 0.5 * math.sin(t * math.tau)
        r = lerp(6.0, 9.0, ease_in_out(breath))
        draw_ring(draw, cx, cy, r, brightness=int(35 + 30 * breath), width=1)


# ===========================================================================
# Tier 1 — Interaction-mode transitions
# ===========================================================================


class WakeCollapse(Animation):
    """IDLE → WAKE: lines converge inward, then lock into focused ring.

    Phase 0–0.45  : parallax lines radially contract toward center
    Phase 0.45–0.75: ring nucleates and brightens
    Phase 0.75–1.0 : slow rotational-lock arc sweep
    """
    duration_ms = 1400
    priority = 3

    def __init__(self, rng: random.Random) -> None:
        super().__init__()
        self._shards: List[Dict[str, float]] = []
        for _ in range(8):
            angle = rng.uniform(0.0, math.tau)
            self._shards.append({
                "angle":  angle,
                "r_start": rng.uniform(22.0, 30.0),
                "bright": rng.randint(90, 160),
            })

    def render(self, draw: ImageDraw.ImageDraw, now_ms: int, width: int, height: int) -> None:
        t = self.progress(now_ms)
        cx, cy = width / 2.0, height / 2.0

        if t < 0.45:
            p = ease_in_out(t / 0.45)
            for sh in self._shards:
                r = lerp(sh["r_start"], 3.0, p)
                x, y = polar_point(cx, cy, r, sh["angle"])
                draw_spark(draw, x, y, brightness=int(sh["bright"] * (1.0 - p * 0.4)), size=1)
            return

        if t < 0.75:
            p = ease_out_cubic((t - 0.45) / 0.30)
            r_ring = lerp(3.0, 11.0, p)
            draw_ring(draw, cx, cy, r_ring, brightness=int(160 + 60 * p), width=1)
            return

        # Rotational lock sweep
        p = ease_in_out((t - 0.75) / 0.25)
        draw_ring(draw, cx, cy, 11.5, brightness=220, width=1)
        lock_arc = lerp(0.0, 300.0, p)
        draw_arc(draw, cx, cy, 13.0, -90.0, -90.0 + lock_arc, brightness=255, width=2)


class WaveformRingLoop(Animation):
    """LISTENING — pulsing waveform ring; amplitude maps to mic energy input.

    Outer ring stays stable. Inner modulation represents collected energy.
    """
    duration_ms = 1800
    priority = 3
    loop = True

    def __init__(self) -> None:
        super().__init__()
        self.mic_amplitude: float = 0.5   # 0..1 — set externally by runtime

    def render(self, draw: ImageDraw.ImageDraw, now_ms: int, width: int, height: int) -> None:
        t = self.progress(now_ms)
        cx, cy = width / 2.0, height / 2.0
        seconds = now_ms / 1000.0

        base_r = 12.0
        amp = lerp(1.5, 5.5, ease_in_out(self.mic_amplitude))

        # Waveform modulated ring — sample radii at discrete angles
        N = 36
        points_outer: List[Tuple[float, float]] = []
        points_inner: List[Tuple[float, float]] = []
        for i in range(N + 1):
            a = (i / N) * math.tau
            wave = math.sin(a * 3 + seconds * math.tau * 1.4) * amp
            ro = base_r + wave
            ri = base_r - wave * 0.4
            points_outer.append(polar_point(cx, cy, max(1.0, ro), a))
            points_inner.append(polar_point(cx, cy, max(1.0, ri), a))

        if len(points_outer) > 1:
            draw.line(points_outer, fill=200, width=1)
        if len(points_inner) > 1:
            draw.line(points_inner, fill=100, width=1)

        # Rotating stabilisation arc — "energy collecting at center"
        draw_arc(draw, cx, cy, base_r + 2.0,
                 (seconds * 90.0) % 360.0,
                 (seconds * 90.0) % 360.0 + 55.0,
                 brightness=255, width=2)

        # Centre spark pulse on beat
        beat = triangle_wave((seconds * 1.5) % 1.0)
        if beat > 0.75:
            draw_spark(draw, cx, cy, brightness=int(140 + 80 * beat), size=1)


class FractureRecombineLoop(Animation):
    """PROCESSING — shards splinter and recombine. Controlled chaos.

    Visually communicates «thinking» — distinct from listening.
    Never still. Converges back when done thinking.
    """
    duration_ms = 3400
    priority = 2
    loop = True

    _SEGMENTS: List[Tuple[float, float, float, float]] = [
        (-11, -5,  -3, -1),
        ( -3, -1,   2,  1),
        (  2,  1,   9,  4),
        ( 10, -7,   3, -2),
        ( -8,  8,  -2,  2),
        (  9,  8,   2,  2),
    ]

    def render(self, draw: ImageDraw.ImageDraw, now_ms: int, width: int, height: int) -> None:
        t = self.progress(now_ms)
        seconds = now_ms / 1000.0
        cx, cy = width / 2.0, height / 2.0

        # Convergence score — shards drift apart then pull back
        phase = math.sin(t * math.tau)      # -1..+1  cycle per loop
        scatter = ease_in_out(abs(phase))    # 0..1 max scatter at t=0.25, 0.75

        jitter_amp = scatter * 3.5
        for idx, (x1, y1, x2, y2) in enumerate(self._SEGMENTS):
            jx = math.sin(seconds * (1.7 + idx * 0.31)) * jitter_amp
            jy = math.cos(seconds * (1.3 + idx * 0.27)) * jitter_amp
            b  = int(160 + scatter * 60)
            draw_shard(draw,
                       cx + x1 + jx, cy + y1 + jy,
                       cx + x2 + jx, cy + y2 + jy,
                       brightness=b, width=1)

        # Convergence ring — brightens as shards pull together
        if scatter < 0.35:
            cv_b = int((0.35 - scatter) / 0.35 * 180)
            draw_ring(draw, cx, cy, 4.0 + scatter * 8.0, brightness=cv_b, width=1)


class RippleEmissionLoop(Animation):
    """SPEAKING — concentric ripples radiate outward with syllable envelope.

    Represents projection / outward energy.
    """
    duration_ms = 900
    priority = 3
    loop = True

    def __init__(self) -> None:
        super().__init__()
        self.speech_amplitude: float = 0.5   # 0..1 — syllable envelope

    def render(self, draw: ImageDraw.ImageDraw, now_ms: int, width: int, height: int) -> None:
        t = self.progress(now_ms)
        cx, cy = width / 2.0, height / 2.0

        # Three staggered ripples per cycle
        for offset in (0.0, 0.33, 0.66):
            pt = (t + offset) % 1.0
            r  = lerp(2.0, 30.0, ease_out_cubic(pt))
            b  = int((1.0 - pt) * lerp(100, 220, ease_in_out(self.speech_amplitude)))
            if b > 4:
                draw_ring(draw, cx, cy, r, brightness=b, width=1)

        # Central brightness pulse with syllable amplitude
        core_b = int(lerp(60, 200, ease_in_out(self.speech_amplitude))
                     * (0.7 + 0.3 * math.sin(t * math.tau * 4)))
        draw_spark(draw, cx, cy, brightness=max(0, min(255, core_b)), size=2)


# ===========================================================================
# Tier 2 — Station personality motifs
# ===========================================================================


class FTBMotif(Animation):
    """From The Backmarker — rotating telemetry arcs + RPM-style sweep.

    Rotating arc pair (telemetry), speedometer sweep, thin racing lines.
    """
    duration_ms = 6000
    priority = 0
    loop = True

    def render(self, draw: ImageDraw.ImageDraw, now_ms: int, width: int, height: int) -> None:
        t = self.progress(now_ms)
        seconds = now_ms / 1000.0
        cx, cy = width / 2.0, height / 2.0

        # Outer telemetry arc pair — counter-rotating
        r_outer = 20.0
        for sign, bright in ((1, 110), (-1, 70)):
            start = math.degrees(seconds * sign * 0.55)
            draw_arc(draw, cx, cy, r_outer, start % 360, (start + 55.0) % 360,
                     brightness=bright, width=1)

        # RPM sweep — fills arc then resets, mimicking rev-limiter
        rpm_t = (t * 2.3) % 1.0          # faster than base loop
        rpm_arc = ease_out_cubic(rpm_t if rpm_t < 0.82 else 1.0 - (rpm_t - 0.82) / 0.18) * 210.0
        draw_arc(draw, cx, cy, 14.5, 200.0, 200.0 + rpm_arc, brightness=190, width=1)

        # Thin racing lines — horizontal streaks low on display
        for row, speed in enumerate((0.9, 1.1, 0.8)):
            y_row = height * 0.62 + row * 5.0
            x_phase = ((seconds * speed * 0.35) % 1.0)
            x_start = x_phase * (width + 20) - 10
            length = 14.0 + row * 4.0
            if 0 < x_start + length < width + 20:
                x0 = max(0.0, x_start)
                x1 = min(float(width - 1), x_start + length)
                draw_shard(draw, x0, y_row, x1, y_row, brightness=55 + row * 15, width=1)


class OracleMotif(Animation):
    """Oracle Kingdom — morphing sigil / sacred geometry.

    Slow angular rotation, petal-like arcs morphing, subtle glow convergence.
    """
    duration_ms = 18000
    priority = 0
    loop = True

    def render(self, draw: ImageDraw.ImageDraw, now_ms: int, width: int, height: int) -> None:
        t = self.progress(now_ms)
        seconds = now_ms / 1000.0
        cx, cy = width / 2.0, height / 2.0

        # Sacred geometry: 6-fold symmetry slowly rotating
        base_angle = seconds * 0.04 * math.tau      # 0.04 rev/s
        N = 6
        r_inner = 7.0
        r_outer = 16.0

        # Morphing between two sigil shapes via sine wave
        morph = 0.5 + 0.5 * math.sin(seconds * 0.12 * math.tau)

        for i in range(N):
            a0 = base_angle + (i / N) * math.tau
            a1 = base_angle + ((i + morph) / N) * math.tau
            p0 = polar_point(cx, cy, r_inner, a0)
            p1 = polar_point(cx, cy, r_outer, a1)
            draw_shard(draw, p0[0], p0[1], p1[0], p1[1],
                       brightness=int(80 + 60 * morph), width=1)

        # Outer halo — opacity breathes very slowly
        halo_b = int(40 + 30 * math.sin(seconds * 0.08 * math.tau))
        draw_ring(draw, cx, cy, r_outer + 2.5, brightness=max(10, halo_b), width=1)

        # Inner pivot point
        draw_spark(draw, cx, cy, brightness=int(90 + 50 * morph), size=1)

        # Slow arc fragment orbiting — adds life
        orbit_a = math.degrees(base_angle * 0.7)
        draw_arc(draw, cx, cy, r_inner + 2.5, orbit_a % 360,
                 (orbit_a + 40.0) % 360, brightness=130, width=1)


class HockeyMotif(Animation):
    """Hockey FM — puck arc trajectories, sharp angular sweeps.

    Clean, minimal, sharp. Not organic.
    """
    duration_ms = 5000
    priority = 0
    loop = True

    def __init__(self, rng: random.Random) -> None:
        super().__init__()
        self._pucks: List[Dict[str, float]] = []
        for _ in range(3):
            self._pucks.append({
                "angle":  rng.uniform(0.0, math.tau),
                "speed":  rng.uniform(0.18, 0.38),
                "radius": rng.uniform(8.0, 20.0),
                "phase":  rng.random(),
            })

    def render(self, draw: ImageDraw.ImageDraw, now_ms: int, width: int, height: int) -> None:
        t = self.progress(now_ms)
        seconds = now_ms / 1000.0
        cx, cy = width / 2.0, height / 2.0

        for puck in self._pucks:
            # Puck follows arc trajectory — sharp angular bounce feel
            progress_p = ((seconds * puck["speed"]) + puck["phase"]) % 1.0
            arc_phase = ease_in_out(progress_p if progress_p < 0.5 else 1.0 - progress_p)
            a = puck["angle"] + arc_phase * math.pi
            x, y = polar_point(cx, cy, puck["radius"] * (0.7 + 0.3 * arc_phase), a)
            draw_spark(draw, x, y, brightness=int(180 + 60 * arc_phase), size=1)

            # Trail — sharp line behind puck
            trail_a = a - 0.25
            tx, ty = polar_point(cx, cy, puck["radius"] * 0.6, trail_a)
            draw_shard(draw, tx, ty, x, y, brightness=int(80 + 40 * arc_phase), width=1)

        # Minimal sweep — clean geometry
        sweep = (t * 1.5 % 1.0)
        sweep_deg = ease_out_cubic(sweep) * 180.0
        draw_arc(draw, cx, cy, 12.5, 180.0, 180.0 + sweep_deg, brightness=100, width=1)


# ===========================================================================
# Cross-fade compositor: smoothly blends two Animation renderers
# ===========================================================================


class MorphBlend:
    """Holds two Animation instances and composites them with a bezier cross-fade.

    Used for all state transitions — nothing ever cuts.

    blend_ms: total duration of the cross-fade in milliseconds.
    """

    def __init__(self, from_anim: Animation, to_anim: Animation, blend_ms: int = 500) -> None:
        self.from_anim  = from_anim
        self.to_anim    = to_anim
        self.blend_ms   = max(50, blend_ms)
        self._start_ms: Optional[int] = None

    def start(self, now_ms: int) -> None:
        self._start_ms = now_ms
        self.to_anim.start(now_ms)

    def progress(self, now_ms: int) -> float:
        if self._start_ms is None:
            return 1.0
        elapsed = now_ms - self._start_ms
        return ease_in_out(clamp(elapsed / self.blend_ms, 0.0, 1.0))

    def done(self, now_ms: int) -> bool:
        return self.progress(now_ms) >= 1.0

    def render(
        self,
        draw: ImageDraw.ImageDraw,
        now_ms: int,
        width: int,
        height: int,
    ) -> None:
        if not HAS_PIL:
            self.to_anim.render(draw, now_ms, width, height)
            return

        t = self.progress(now_ms)

        if t <= 0.0:
            self.from_anim.render(draw, now_ms, width, height)
            return
        if t >= 1.0:
            self.to_anim.render(draw, now_ms, width, height)
            return

        # Render both into separate L-mode frames then blend pixel-by-pixel
        from PIL import Image as _Image, ImageDraw as _IDraw

        f_from = _Image.new("L", (width, height), 0)
        d_from = _IDraw.Draw(f_from)
        self.from_anim.render(d_from, now_ms, width, height)

        f_to = _Image.new("L", (width, height), 0)
        d_to = _IDraw.Draw(f_to)
        self.to_anim.render(d_to, now_ms, width, height)

        blended = _Image.blend(f_from, f_to, alpha=t)
        draw._image.paste(blended)  # type: ignore[attr-defined]


# ===========================================================================
# Tier-2 station registry: station_id → motif factory
# ===========================================================================


# Plugin motion-profile contract — populated at runtime by station registration
_STATION_MOTION_PROFILES: Dict[str, Dict[str, Any]] = {}


def register_station_motion_profile(station_id: str, profile: Dict[str, Any]) -> None:
    """Called by meta-plugins at load time to register their OLED motion profile."""
    _STATION_MOTION_PROFILES[station_id.lower().strip()] = profile


def _motif_for_station(station_id: str, rng: random.Random) -> Optional[Animation]:
    sid = (station_id or "").lower().strip()

    # Check registered plugin profiles first
    if sid in _STATION_MOTION_PROFILES:
        mp = _STATION_MOTION_PROFILES[sid].get("motion_profile", "orbital")
        if mp == "radial":
            return OracleMotif()
        if mp == "fracture":
            return FractureRecombineLoop()
        if mp == "orbital":
            return FTBMotif()

    # Hard-coded well-known station IDs
    if sid in ("ftb", "from_the_backmarker", "algotradingfm", "algofm"):
        return FTBMotif()
    if sid in ("oracle", "oracle_kingdom", "ok"):
        return OracleMotif()
    if sid in ("hockey", "hockeyfm", "hockey_fm"):
        return HockeyMotif(rng)
    return None


# ---------------------------------------------------------------------------
# Display backends
# ---------------------------------------------------------------------------


class DisplayBackend:
    def show(self, frame: Image.Image) -> None:
        raise NotImplementedError

    def close(self) -> None:
        pass


class HeadlessBackend(DisplayBackend):
    def __init__(self, preview_path: Optional[str] = None, preview_every_n: int = 4) -> None:
        self.preview_path = Path(preview_path).expanduser() if preview_path else None
        self.preview_every_n = max(1, preview_every_n)
        self._counter = 0

    def show(self, frame: Image.Image) -> None:
        if self.preview_path is None:
            return
        self._counter += 1
        if self._counter % self.preview_every_n != 0:
            return
        self.preview_path.parent.mkdir(parents=True, exist_ok=True)
        frame.save(self.preview_path)


class LumaSpiBackend(DisplayBackend):
    def __init__(
        self,
        width: int,
        height: int,
        driver: str,
        spi_port: int,
        spi_device: int,
        dc_pin: int,
        rst_pin: int,
        bus_speed_hz: int,
        rotate_quadrants: int,
    ) -> None:
        if not HAS_LUMA:
            raise RuntimeError("luma.oled is not installed. Use --simulate or install luma.oled.")

        serial = spi(
            port=spi_port,
            device=spi_device,
            gpio_DC=dc_pin,
            gpio_RST=rst_pin,
            bus_speed_hz=bus_speed_hz,
        )
        driver_name = (driver or "ssd1306").strip().lower()
        cls = getattr(oled_device, driver_name, None)
        if cls is None:
            cls = oled_device.ssd1309
            print(f"[oled] unknown driver '{driver_name}', falling back to ssd1309")

        self.device = cls(serial, width=width, height=height, rotate=rotate_quadrants)
        self.mode = getattr(self.device, "mode", "1")

    def show(self, frame: Image.Image) -> None:
        out = frame
        if self.mode == "1":
            out = frame.convert("1")
        elif self.mode == "L":
            out = frame.convert("L")
        self.device.display(out)

    def close(self) -> None:
        try:
            self.device.cleanup()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Scheduler and daemon
# ---------------------------------------------------------------------------


# Tier-0 power states
T0_STATES = frozenset({"off", "booting", "idle", "active", "muted", "error"})
# Tier-1 interaction modes
T1_MODES  = frozenset({"home", "station_selected", "simulation",
                        "listening", "speaking", "processing"})


@dataclass
class SoulConfig:
    width: int = 128
    height: int = 64
    fps: int = 20
    udp_host: str = DEFAULT_UDP_HOST
    udp_port: int = DEFAULT_UDP_PORT
    ambient_style: str = "field_drift"
    boot_ritual: bool = True
    simulate: bool = False
    preview_path: Optional[str] = None
    driver: str = "ssd1309"
    spi_port: int = 0
    spi_device: int = 0
    spi_speed_hz: int = 8_000_000
    dc_pin: int = 25
    rst_pin: int = 27
    rotate_degrees: int = 0
    seed: int = 1337


class SoulScheduler:
    """3-tier state machine for the transparent OLED soul display.

    Frame composition:
        base_motion  (Tier-0 loop)         — always rendered at full brightness
        station_motif (Tier-2 loop)        — blended at low alpha beneath base
        interaction_layer (Tier-1 ritual)  — rendered on top when active
        active_ritual (one-shot overlay)   — highest priority, rendered last
    """

    def __init__(self, cfg: SoulConfig) -> None:
        self.cfg  = cfg
        self.rng  = random.Random(cfg.seed)

        # Tier-0
        self._t0: str = "idle"
        self._base_loop: Animation = self._make_base_loop()
        self._base_loop.start(self._now_ms())

        # Tier-1
        self._t1: str = "home"
        self._t1_loop: Optional[Animation] = None   # active while T1 != "home"

        # Tier-2
        self._station_id: str = ""
        self._station_motif: Optional[Animation] = None
        self._motif_morph: Optional[MorphBlend] = None  # cross-fade in/out

        # One-shot ritual queue
        self.active_ritual: Optional[Animation] = None
        self.pending: Deque[Animation] = deque()

        # Coalescing accumulators
        self._volume_acc     = 0
        self._volume_last_ms = 0
        self._scroll_last_ms = 0
        self._scroll_last_dir = 0

        # Live amplitude feeds for reactive loops
        self._mic_amp:    float = 0.0
        self._speech_amp: float = 0.0

    # ── helpers ──────────────────────────────────────────────────────────────

    def _now_ms(self) -> int:
        return int(time.monotonic() * 1000.0)

    def _make_base_loop(self) -> Animation:
        style = getattr(self.cfg, "ambient_style", "field_drift")
        if self._t0 == "muted":
            return MutedPulse()
        if self._t0 == "error":
            return ErrorLoop()
        if style == "orbit_calm":
            return OrbitCalmLoop()
        if style == "breathing_halo":
            return BreathingHaloLoop(self.rng)
        return FieldDriftLoop(self.rng)   # default

    def _make_t1_loop(self, mode: str) -> Optional[Animation]:
        if mode == "listening":
            loop = WaveformRingLoop()
            loop.mic_amplitude = self._mic_amp
            return loop
        if mode == "processing":
            return FractureRecombineLoop()
        if mode == "speaking":
            loop = RippleEmissionLoop()
            loop.speech_amplitude = self._speech_amp
            return loop
        return None

    # ── tier setters ─────────────────────────────────────────────────────────

    def set_power_state(self, state: str, now_ms: Optional[int] = None) -> None:
        """Set Tier-0 power state. Morphs the base loop."""
        state = state.strip().lower()
        if state not in T0_STATES:
            state = "idle"
        if state == self._t0:
            return
        now = now_ms or self._now_ms()
        self._t0 = state
        new_loop = self._make_base_loop()
        new_loop.start(now)
        # Morph — 600 ms cross-fade for power state changes
        self._base_loop = new_loop   # no pixel-blend for loops (perf); swap directly

    def set_mode(self, mode: str, now_ms: Optional[int] = None) -> None:
        """Set Tier-1 interaction mode."""
        mode = mode.strip().lower()
        if mode not in T1_MODES:
            mode = "home"
        if mode == self._t1:
            return
        now = now_ms or self._now_ms()
        self._t1 = mode
        new_t1 = self._make_t1_loop(mode)
        if new_t1 is not None:
            new_t1.start(now)
        self._t1_loop = new_t1

    def set_station(self, station_id: str, now_ms: Optional[int] = None) -> None:
        """Set Tier-2 station personality motif with morph cross-fade."""
        sid = (station_id or "").strip().lower()
        if sid == self._station_id:
            return
        now = now_ms or self._now_ms()
        self._station_id = sid
        old_motif = self._station_motif
        new_motif = _motif_for_station(sid, self.rng)
        if new_motif is not None:
            new_motif.start(now)
        self._station_motif = new_motif
        if old_motif is not None and new_motif is not None:
            self._motif_morph = MorphBlend(old_motif, new_motif, blend_ms=800)
            self._motif_morph.start(now)
        else:
            self._motif_morph = None

    # ── legacy one-arg set_state (backward compat) ───────────────────────────

    def set_state(self, state: str, now_ms: Optional[int] = None) -> None:
        """Backward-compat: maps old state strings to Tier-0/Tier-1 calls."""
        s = (state or "ambient").strip().lower()
        _t0_map = {"ambient": "idle", "idle": "idle", "error": "error", "muted": "muted"}
        _t1_map = {"listening": "listening", "thinking": "processing", "speaking": "speaking"}
        if s in _t0_map:
            self.set_power_state(_t0_map[s], now_ms)
        if s in _t1_map:
            self.set_mode(_t1_map[s], now_ms)
        elif s not in _t1_map and s not in ("listening", "thinking"):
            self.set_mode("home", now_ms)

    # ── ritual queue ──────────────────────────────────────────────────────────

    def _enqueue_or_preempt(self, anim: Animation, now_ms: int) -> None:
        anim.start(now_ms)
        if self.active_ritual is None:
            self.active_ritual = anim
            return
        if anim.priority > self.active_ritual.priority:
            self.pending.appendleft(self.active_ritual)
            self.active_ritual = anim
        else:
            self.pending.append(anim)

    def _flush_coalesced(self, now_ms: int) -> None:
        if self._volume_acc != 0 and (now_ms - self._volume_last_ms) >= 90:
            direction = 1 if self._volume_acc > 0 else -1
            intensity = min(4, max(1, abs(self._volume_acc)))
            self._enqueue_or_preempt(VolumeTilt(direction=direction, intensity=intensity), now_ms)
            self._volume_acc = 0

    # ── event router ─────────────────────────────────────────────────────────

    def handle_event(self, payload: Dict[str, Any], now_ms: Optional[int] = None) -> None:
        now = now_ms if now_ms is not None else self._now_ms()
        etype_raw = str(payload.get("type", "")).strip().lower()
        etype = etype_raw.replace("-", "_").replace(" ", "_")
        station_id = str(payload.get("station_id", "")).strip()

        # ── Tier-0: power / system ────────────────────────────────────────
        if etype in ("boot", "startup"):
            self.set_power_state("booting", now)
            self._enqueue_or_preempt(BootIgnition(), now)
            return
        if etype in ("wake",):
            self.set_power_state("active", now)
            self._enqueue_or_preempt(WakeCollapse(self.rng), now)
            return
        if etype in ("sleep", "shutdown"):
            self.set_power_state("off", now)
            self._enqueue_or_preempt(PortalClose(self.rng), now)
            return
        if etype in ("mute", "muted"):
            self.set_power_state("muted", now)
            self._enqueue_or_preempt(DampenOff(), now)
            return
        if etype in ("unmute",):
            self.set_power_state("active", now)
            self._enqueue_or_preempt(RipplesOn(), now)
            return
        if etype in ("error", "fatal_error", "backend_error"):
            self.set_power_state("error", now)
            self._enqueue_or_preempt(Fracture(), now)
            return
        if etype in ("clear_error", "error_clear", "recover"):
            self.set_power_state("active", now)
            self._enqueue_or_preempt(Ping(), now)
            return

        # ── Tier-1: interaction mode ──────────────────────────────────────
        if etype in ("audio_cli_on", "listening_start", "mic_on", "wake_word_detected"):
            self.set_mode("listening", now)
            self._enqueue_or_preempt(RipplesOn(), now)
            return
        if etype in ("audio_cli_off", "listening_stop", "mic_off"):
            self.set_mode("home", now)
            self._enqueue_or_preempt(DampenOff(), now)
            return

        if etype in ("thinking_start", "llm_busy_start", "busy_start"):
            self.set_mode("processing", now)
            return
        if etype in ("thinking_end", "llm_busy_end", "busy_end"):
            self.set_mode("home", now)
            self._enqueue_or_preempt(ResolvePulse(), now)
            return

        if etype in ("tts_start", "speaking_start", "speech_start"):
            self.set_mode("speaking", now)
            return
        if etype in ("tts_end", "speaking_end", "speech_end", "tts_done"):
            self.set_mode("home", now)
            self._enqueue_or_preempt(ResolvePulse(), now)
            return

        # Live amplitude feeds
        if etype == "mic_amplitude":
            try:
                self._mic_amp = float(clamp(float(payload.get("value", 0.5)), 0.0, 1.0))
                if isinstance(self._t1_loop, WaveformRingLoop):
                    self._t1_loop.mic_amplitude = self._mic_amp
            except Exception:
                pass
            return
        if etype == "speech_amplitude":
            try:
                self._speech_amp = float(clamp(float(payload.get("value", 0.5)), 0.0, 1.0))
                if isinstance(self._t1_loop, RippleEmissionLoop):
                    self._t1_loop.speech_amplitude = self._speech_amp
            except Exception:
                pass
            return

        # ── Tier-2: station selection ─────────────────────────────────────
        if etype in ("enter_station", "station_launch", "station_start", "play",
                     "station_launch_requested", "station_selected"):
            self.set_power_state("active", now)
            self.set_mode("station_selected", now)
            if station_id:
                self.set_station(station_id, now)
            self._enqueue_or_preempt(PortalOpen(), now)
            return
        if etype in ("simulation_start", "sim_start"):
            self.set_mode("simulation", now)
            self._enqueue_or_preempt(ScanLock(), now)
            return
        if etype in ("exit_station", "station_stop", "stop", "station_stopped"):
            self.set_mode("home", now)
            self.set_station("", now)
            self._enqueue_or_preempt(PortalClose(self.rng), now)
            return

        # ── Navigation ────────────────────────────────────────────────────
        if etype in ("loading_in", "loading_out", "loading_start", "loading_switch", "transition"):
            self._enqueue_or_preempt(ScanLock(), now)
            return

        if etype in ("confirm", "tap", "select", "ok"):
            self._enqueue_or_preempt(Ping(), now)
            return

        if etype in ("volume_delta", "volume", "volume_change"):
            delta = payload.get("delta", 0)
            try:
                delta_int = int(delta)
            except Exception:
                delta_int = 0
            if delta_int != 0:
                self._volume_acc += delta_int
                self._volume_last_ms = now
            return

        if etype in ("station_nudge_left", "nudge_left", "scroll_left", "swipe_left"):
            if (now - self._scroll_last_ms) > 85 or self._scroll_last_dir != -1:
                self._enqueue_or_preempt(SideWind(direction=-1), now)
                self._scroll_last_ms = now
                self._scroll_last_dir = -1
            return

        if etype in ("station_nudge_right", "nudge_right", "scroll_right", "swipe_right"):
            if (now - self._scroll_last_ms) > 85 or self._scroll_last_dir != 1:
                self._enqueue_or_preempt(SideWind(direction=1), now)
                self._scroll_last_ms = now
                self._scroll_last_dir = 1
            return

    # ── frame renderer ────────────────────────────────────────────────────────

    def render_frame(self, now_ms: Optional[int] = None) -> "Image.Image":  # type: ignore[name-defined]
        now = now_ms if now_ms is not None else self._now_ms()
        self._flush_coalesced(now)

        frame = Image.new("L", (self.cfg.width, self.cfg.height), 0)
        draw  = ImageDraw.Draw(frame)

        # ── Layer 1: Tier-2 station motif (background, dimmed) ────────────
        if self._motif_morph is not None:
            self._motif_morph.render(draw, now, self.cfg.width, self.cfg.height)
            if self._motif_morph.done(now):
                self._motif_morph = None
        elif self._station_motif is not None:
            # Render motif at ~35% brightness by compositing on frame
            if HAS_PIL:
                from PIL import Image as _I, ImageDraw as _ID
                f2 = _I.new("L", (self.cfg.width, self.cfg.height), 0)
                d2 = _ID.Draw(f2)
                self._station_motif.render(d2, now, self.cfg.width, self.cfg.height)
                # Darken the motif layer
                blended = _I.blend(frame, f2, alpha=0.35)
                frame.paste(blended)
                draw = ImageDraw.Draw(frame)
            else:
                self._station_motif.render(draw, now, self.cfg.width, self.cfg.height)

        # ── Layer 2: Tier-0 base motion loop ──────────────────────────────
        self._base_loop.render(draw, now, self.cfg.width, self.cfg.height)

        # ── Layer 3: Tier-1 interaction loop (on top of base) ─────────────
        if self._t1_loop is not None:
            self._t1_loop.render(draw, now, self.cfg.width, self.cfg.height)

        # ── Layer 4: One-shot ritual (highest priority overlay) ───────────
        if self.active_ritual is not None:
            self.active_ritual.render(draw, now, self.cfg.width, self.cfg.height)
            if self.active_ritual.done(now):
                self.active_ritual = None

        if self.active_ritual is None and self.pending:
            nxt = self.pending.popleft()
            nxt.start(now)
            self.active_ritual = nxt
            self.active_ritual.render(draw, now, self.cfg.width, self.cfg.height)

        return frame


class OledSoulDaemon:
    def __init__(self, cfg: SoulConfig) -> None:
        if not HAS_PIL:
            raise RuntimeError("Pillow is required for oled_soul_daemon.py (pip install Pillow)")
        self.cfg = cfg
        self.scheduler = SoulScheduler(cfg)
        self.running = False

        rotate_quadrants = (cfg.rotate_degrees // 90) % 4
        if cfg.simulate:
            self.backend: DisplayBackend = HeadlessBackend(preview_path=cfg.preview_path)
            print("[oled] running in simulation mode")
        else:
            try:
                self.backend = LumaSpiBackend(
                    width=cfg.width,
                    height=cfg.height,
                    driver=cfg.driver,
                    spi_port=cfg.spi_port,
                    spi_device=cfg.spi_device,
                    dc_pin=cfg.dc_pin,
                    rst_pin=cfg.rst_pin,
                    bus_speed_hz=cfg.spi_speed_hz,
                    rotate_quadrants=rotate_quadrants,
                )
                print(f"[oled] SPI backend ready: driver={cfg.driver} {cfg.width}x{cfg.height}")
            except Exception as exc:
                import traceback as _tb
                print(f"[oled] SPI backend failed ({type(exc).__name__}: {exc})")
                _tb.print_exc()
                self.backend = HeadlessBackend(preview_path=cfg.preview_path)

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((cfg.udp_host, cfg.udp_port))
        self.sock.setblocking(False)
        print(f"[oled] listening for UDP events on {cfg.udp_host}:{cfg.udp_port}")

    def _poll_udp(self, now_ms: int) -> None:
        while True:
            try:
                packet, _addr = self.sock.recvfrom(8192)
            except BlockingIOError:
                break
            except Exception as exc:
                print(f"[oled] UDP read error: {exc}")
                break

            if not packet:
                continue
            try:
                payload = json.loads(packet.decode("utf-8").strip())
                if isinstance(payload, dict):
                    self.scheduler.handle_event(payload, now_ms=now_ms)
                elif isinstance(payload, list):
                    for item in payload:
                        if isinstance(item, dict):
                            self.scheduler.handle_event(item, now_ms=now_ms)
            except Exception as exc:
                print(f"[oled] malformed UDP packet: {exc}")

    def run(self) -> None:
        self.running = True
        frame_time = 1.0 / float(max(1, self.cfg.fps))
        now_ms = int(time.monotonic() * 1000.0)
        if self.cfg.boot_ritual:
            self.scheduler.handle_event({"type": "boot"}, now_ms=now_ms)

        try:
            while self.running:
                started = time.perf_counter()
                now_ms = int(time.monotonic() * 1000.0)
                self._poll_udp(now_ms)
                frame = self.scheduler.render_frame(now_ms=now_ms)
                self.backend.show(frame)
                elapsed = time.perf_counter() - started
                sleep_for = frame_time - elapsed
                if sleep_for > 0:
                    time.sleep(sleep_for)
        except KeyboardInterrupt:
            print("\n[oled] stopping (keyboard interrupt)")
        finally:
            self.close()

    def close(self) -> None:
        self.running = False
        try:
            self.sock.close()
        except Exception:
            pass
        self.backend.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _positive_int(value: str) -> int:
    iv = int(value)
    if iv <= 0:
        raise argparse.ArgumentTypeError("must be > 0")
    return iv


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Transparent OLED soul-display daemon")
    p.add_argument("--udp-host", default=DEFAULT_UDP_HOST, help="UDP listen host")
    p.add_argument("--udp-port", type=_positive_int, default=DEFAULT_UDP_PORT, help="UDP listen port")
    p.add_argument("--fps", type=_positive_int, default=20, help="Target render fps")
    p.add_argument("--width", type=_positive_int, default=128, help="Display width")
    p.add_argument("--height", type=_positive_int, default=64, help="Display height")
    p.add_argument("--ambient",
                   choices=("field_drift", "breathing_halo", "orbit_calm"),
                   default="field_drift",
                   help="Ambient base-motion style (default: field_drift)")

    p.add_argument("--simulate", action="store_true", help="Run without SPI hardware")
    p.add_argument("--preview-path", default="", help="Optional PNG output path in simulation mode")

    p.add_argument("--driver", default="ssd1309", help="luma.oled driver name")
    p.add_argument("--spi-port", type=int, default=0, help="SPI bus index")
    p.add_argument("--spi-device", type=int, default=0, help="SPI device index")
    p.add_argument("--spi-speed-hz", type=_positive_int, default=8000000, help="SPI bus speed")
    p.add_argument("--dc-pin", type=int, default=24, help="GPIO DC pin")
    p.add_argument("--rst-pin", type=int, default=27, help="GPIO RST pin")
    p.add_argument("--rotate", type=int, default=0, help="Rotation degrees (0/90/180/270)")
    p.add_argument("--no-boot", action="store_true", help="Disable boot ritual at daemon startup")
    return p


def main() -> None:
    args = build_arg_parser().parse_args()
    cfg = SoulConfig(
        width=args.width,
        height=args.height,
        fps=args.fps,
        udp_host=args.udp_host,
        udp_port=args.udp_port,
        ambient_style=args.ambient,
        boot_ritual=not args.no_boot,
        simulate=args.simulate,
        preview_path=args.preview_path or None,
        driver=args.driver,
        spi_port=args.spi_port,
        spi_device=args.spi_device,
        spi_speed_hz=args.spi_speed_hz,
        dc_pin=args.dc_pin,
        rst_pin=args.rst_pin,
        rotate_degrees=args.rotate,
    )
    daemon = OledSoulDaemon(cfg)
    daemon.run()


if __name__ == "__main__":
    main()
