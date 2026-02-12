# your_runtime.py
# Shim to satisfy plugins that were written against "your_runtime".
import sys
import os
import time

sys.path.append(".")

# Try to import from runtime (production), fallback to local definitions
try:
    from runtime import log, now_ts, event_q, StationEvent, notification_q
except ImportError:
    # Fallback: define locally
    import time
    
    event_q = None
    notification_q = None
    StationEvent = None
    
    def now_ts() -> int:
        return int(time.time())

    def log(role: str, msg: str) -> None:
        ts = time.strftime("%H:%M:%S")
        print(f"[{role.upper():>8} {ts}] {msg}", flush=True)


def get_visual_model_config() -> dict:
    """
    Get visual model configuration from environment variables.
    Returns a dict with keys: model_type, local_model, api_provider, api_model, 
    api_key, api_endpoint, max_image_size, image_quality.
    """
    return {
        "model_type": os.getenv("VISUAL_MODEL_TYPE", "local"),
        "local_model": os.getenv("VISUAL_MODEL_LOCAL", ""),
        "api_provider": os.getenv("VISUAL_MODEL_API_PROVIDER", ""),
        "api_model": os.getenv("VISUAL_MODEL_API_MODEL", ""),
        "api_key": os.getenv("VISUAL_MODEL_API_KEY", ""),
        "api_endpoint": os.getenv("VISUAL_MODEL_API_ENDPOINT", ""),
        "max_image_size": int(os.getenv("VISUAL_MODEL_MAX_IMAGE_SIZE", "1024")),
        "image_quality": int(os.getenv("VISUAL_MODEL_IMAGE_QUALITY", "85")),
    }
