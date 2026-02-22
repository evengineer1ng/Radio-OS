#!/usr/bin/env python3
"""
Send one event to the OLED soul display daemon via UDP.
"""

from __future__ import annotations

import argparse
import json
from typing import Any, Dict

try:
    from tools.oled_event_client import send_oled_event, DEFAULT_UDP_HOST, DEFAULT_UDP_PORT
except Exception:
    from oled_event_client import send_oled_event, DEFAULT_UDP_HOST, DEFAULT_UDP_PORT  # type: ignore


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Send OLED daemon event")
    p.add_argument("--host", default=DEFAULT_UDP_HOST, help="UDP host")
    p.add_argument("--port", type=int, default=DEFAULT_UDP_PORT, help="UDP port")
    p.add_argument("--type", default="", help="Event type")
    p.add_argument("--delta", type=int, default=0, help="Optional delta (volume)")
    p.add_argument("--station-id", default="", help="Optional station id")
    p.add_argument("--json", default="", help="Raw JSON event payload (overrides --type args)")
    return p


def main() -> None:
    args = build_arg_parser().parse_args()

    if args.json:
        payload: Dict[str, Any] = json.loads(args.json)
        if not isinstance(payload, dict):
            raise ValueError("JSON payload must be an object")
    else:
        if not args.type:
            raise ValueError("Provide --type or --json")
        payload = {"type": args.type}
        if args.delta:
            payload["delta"] = args.delta
        if args.station_id:
            payload["station_id"] = args.station_id

    send_oled_event(payload, host=args.host, port=args.port)
    print(f"sent: {payload}")


if __name__ == "__main__":
    main()
