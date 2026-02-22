#!/usr/bin/env python3
"""Lightweight UDP client for OLED soul-display events."""

from __future__ import annotations

import json
import socket
from typing import Any, Dict

DEFAULT_UDP_HOST = "127.0.0.1"
DEFAULT_UDP_PORT = 5115


def send_oled_event(
    event: Dict[str, Any],
    host: str = DEFAULT_UDP_HOST,
    port: int = DEFAULT_UDP_PORT,
) -> None:
    payload = json.dumps(event, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.sendto(payload, (host, port))
    finally:
        sock.close()

