#!/usr/bin/env python3
"""
Transparent OLED "Soul Display" daemon.

Renders abstract motion glyphs on a 128x64 OLED and reacts to UDP JSON events.
Designed for SPI-connected displays on Raspberry Pi, with headless fallback.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import socket
import time
from dataclasses import dataclass
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
            cls = oled_device.ssd1306
            print(f"[oled] unknown driver '{driver_name}', falling back to ssd1306")

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


STATE_PRIORITY = {
    "ambient": 0,
    "transition": 1,
    "thinking": 2,
    "listening": 3,
    "error": 4,
}


@dataclass
class SoulConfig:
    width: int = 128
    height: int = 64
    fps: int = 20
    udp_host: str = DEFAULT_UDP_HOST
    udp_port: int = DEFAULT_UDP_PORT
    ambient_style: str = "breathing_halo"
    boot_ritual: bool = True
    simulate: bool = False
    preview_path: Optional[str] = None
    driver: str = "ssd1306"
    spi_port: int = 0
    spi_device: int = 0
    spi_speed_hz: int = 12_000_000
    dc_pin: int = 24
    rst_pin: int = 25
    rotate_degrees: int = 0
    seed: int = 1337


class SoulScheduler:
    def __init__(self, cfg: SoulConfig) -> None:
        self.cfg = cfg
        self.rng = random.Random(cfg.seed)
        self.state = "ambient"
        self.state_loop: Animation = self._make_state_loop("ambient")
        self.state_loop.start(self._now_ms())

        self.active_ritual: Optional[Animation] = None
        self.pending: Deque[Animation] = deque()

        self._volume_acc = 0
        self._volume_last_ms = 0
        self._scroll_last_ms = 0
        self._scroll_last_dir = 0

    def _now_ms(self) -> int:
        return int(time.monotonic() * 1000.0)

    def _make_state_loop(self, state: str) -> Animation:
        if state == "listening":
            return ListeningLoop()
        if state == "thinking":
            return ThinkingLoop()
        if state == "error":
            return ErrorLoop()
        if self.cfg.ambient_style == "orbit_calm":
            return OrbitCalmLoop()
        return BreathingHaloLoop(self.rng)

    def set_state(self, state: str, now_ms: Optional[int] = None) -> None:
        state = (state or "ambient").strip().lower()
        if state not in ("ambient", "listening", "thinking", "error"):
            state = "ambient"
        if state == self.state:
            return
        self.state = state
        self.state_loop = self._make_state_loop(state)
        self.state_loop.start(now_ms if now_ms is not None else self._now_ms())

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

    def handle_event(self, payload: Dict[str, Any], now_ms: Optional[int] = None) -> None:
        now = now_ms if now_ms is not None else self._now_ms()
        etype_raw = str(payload.get("type", "")).strip().lower()
        etype = etype_raw.replace("-", "_").replace(" ", "_")

        if etype in ("boot", "wake", "startup"):
            self.set_state("ambient", now)
            self._enqueue_or_preempt(BootIgnition(), now)
            return
        if etype in ("sleep", "shutdown"):
            self._enqueue_or_preempt(PortalClose(self.rng), now)
            return

        if etype in ("enter_station", "station_launch", "station_start", "play", "station_launch_requested"):
            self._enqueue_or_preempt(PortalOpen(), now)
            return
        if etype in ("exit_station", "station_stop", "stop", "station_stopped"):
            self._enqueue_or_preempt(PortalClose(self.rng), now)
            return

        if etype in ("loading_in", "loading_out", "loading_start", "loading_switch", "transition"):
            self._enqueue_or_preempt(ScanLock(), now)
            return

        if etype in ("audio_cli_on", "listening_start", "mic_on", "wake_word_detected"):
            self.set_state("listening", now)
            self._enqueue_or_preempt(RipplesOn(), now)
            return
        if etype in ("audio_cli_off", "listening_stop", "mic_off"):
            self.set_state("ambient", now)
            self._enqueue_or_preempt(DampenOff(), now)
            return

        if etype in ("thinking_start", "llm_busy_start", "busy_start"):
            self.set_state("thinking", now)
            return
        if etype in ("thinking_end", "llm_busy_end", "busy_end"):
            self.set_state("ambient", now)
            self._enqueue_or_preempt(ResolvePulse(), now)
            return

        if etype in ("error", "fatal_error", "backend_error"):
            self.set_state("error", now)
            self._enqueue_or_preempt(Fracture(), now)
            return
        if etype in ("clear_error", "error_clear", "recover"):
            self.set_state("ambient", now)
            self._enqueue_or_preempt(Ping(), now)
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

    def render_frame(self, now_ms: Optional[int] = None) -> Image.Image:
        now = now_ms if now_ms is not None else self._now_ms()
        self._flush_coalesced(now)

        frame = Image.new("L", (self.cfg.width, self.cfg.height), 0)
        draw = ImageDraw.Draw(frame)

        if self.active_ritual is not None:
            self.active_ritual.render(draw, now, self.cfg.width, self.cfg.height)
            if self.active_ritual.done(now):
                self.active_ritual = None

        if self.active_ritual is None:
            if self.pending:
                nxt = self.pending.popleft()
                nxt.start(now)
                self.active_ritual = nxt
                self.active_ritual.render(draw, now, self.cfg.width, self.cfg.height)
            else:
                self.state_loop.render(draw, now, self.cfg.width, self.cfg.height)

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
                print(f"[oled] SPI backend failed ({exc}); switching to simulation mode")
                self.backend = HeadlessBackend(preview_path=cfg.preview_path)

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
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
    p.add_argument("--ambient", choices=("breathing_halo", "orbit_calm"), default="breathing_halo", help="Ambient style")

    p.add_argument("--simulate", action="store_true", help="Run without SPI hardware")
    p.add_argument("--preview-path", default="", help="Optional PNG output path in simulation mode")

    p.add_argument("--driver", default="ssd1306", help="luma.oled driver name")
    p.add_argument("--spi-port", type=int, default=0, help="SPI bus index")
    p.add_argument("--spi-device", type=int, default=0, help="SPI device index")
    p.add_argument("--spi-speed-hz", type=_positive_int, default=12000000, help="SPI bus speed")
    p.add_argument("--dc-pin", type=int, default=24, help="GPIO DC pin")
    p.add_argument("--rst-pin", type=int, default=25, help="GPIO RST pin")
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
