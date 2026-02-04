# your_runtime.py
# Shim to satisfy plugins that were written against "your_runtime".
# your_runtime.py
# Shim for plugins expecting "your_runtime"
import sys
sys.path.append(".")

from shell import StationEvent, event_q, log, now_ts

from runtime import log, now_ts, event_q, StationEvent

import time

def now_ts() -> int:
    return int(time.time())

def log(role: str, msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    print(f"[{role.upper():>8} {ts}] {msg}", flush=True)

# The plugin should import these from the real runtime at runtime, but as a shim
# we provide names and let the plugin call back into the engine by passing queues/events.
