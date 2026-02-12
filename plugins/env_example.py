"""
Example plugin showing how to use Radio OS environment variables.

This plugin demonstrates how plugins can access configuration through
environment variables set in the Shell Settings > Environment panel.
"""

import os
from typing import Dict, Any

PLUGIN_NAME = "env_example"
PLUGIN_DESC = "Example plugin demonstrating environment variable usage"
IS_FEED = True

DEFAULT_CONFIG = {
    "enabled": True,
    "message": "Hello from environment example!"
}

def feed_worker(stop_event, mem: Dict[str, Any], cfg: Dict[str, Any], runtime=None):
    """
    Example feed worker that uses environment variables.
    
    Shows how plugins can access:
    - Radio OS paths and configuration
    - API keys and endpoints
    - Custom environment settings
    """
    from your_runtime import event_q, StationEvent, log
    
    import time
    
    # Access Radio OS environment variables
    radio_root = os.getenv("RADIO_OS_ROOT", "Unknown")
    voices_dir = os.getenv("RADIO_OS_VOICES", "Not configured")
    plugins_dir = os.getenv("RADIO_OS_PLUGINS", "Not configured")
    
    # Model configuration
    context_model = os.getenv("CONTEXT_MODEL", "qwen3:8b")
    host_model = os.getenv("HOST_MODEL", "qwen3:8b")
    ollama_endpoint = os.getenv("OLLAMA_ENDPOINT", "http://localhost:11434")
    
    # Station-specific paths (automatically set by Radio OS)
    station_dir = os.getenv("STATION_DIR", "Unknown")
    station_db = os.getenv("STATION_DB_PATH", "Unknown")
    station_memory = os.getenv("STATION_MEMORY_PATH", "Unknown")
    
    # API keys (handle securely)
    has_openai = bool(os.getenv("OPENAI_API_KEY", "").strip())
    has_anthropic = bool(os.getenv("ANTHROPIC_API_KEY", "").strip())
    has_google = bool(os.getenv("GOOGLE_API_KEY", "").strip())
    
    log(f"[ENV Example] Starting with environment config:")
    log(f"  Radio OS Root: {radio_root}")
    log(f"  Voices Dir: {voices_dir}")
    log(f"  Plugins Dir: {plugins_dir}")
    log(f"  Context Model: {context_model}")
    log(f"  Host Model: {host_model}")
    log(f"  Ollama Endpoint: {ollama_endpoint}")
    log(f"  Station Dir: {station_dir}")
    log(f"  Has OpenAI Key: {has_openai}")
    log(f"  Has Anthropic Key: {has_anthropic}")
    log(f"  Has Google Key: {has_google}")
    
    # Generate a status report
    status_parts = []
    status_parts.append(f"Radio OS running from: {radio_root}")
    status_parts.append(f"Station directory: {os.path.basename(station_dir)}")
    status_parts.append(f"Using models: {context_model} (context), {host_model} (host)")
    
    api_providers = []
    if has_openai: api_providers.append("OpenAI")
    if has_anthropic: api_providers.append("Anthropic")
    if has_google: api_providers.append("Google")
    
    if api_providers:
        status_parts.append(f"Available API providers: {', '.join(api_providers)}")
    else:
        status_parts.append("Using local Ollama models only")
    
    status_message = " • ".join(status_parts)
    
    # Send environment status to the event queue
    event_q.put(StationEvent(
        role="feed",
        source="env_example",
        content_blocks=[{
            "text": f"Environment Configuration Status: {status_message}",
            "metadata": {
                "type": "environment_status",
                "radio_root": radio_root,
                "models": {
                    "context": context_model,
                    "host": host_model,
                    "endpoint": ollama_endpoint
                },
                "api_providers": api_providers,
                "station_paths": {
                    "dir": station_dir,
                    "db": station_db,
                    "memory": station_memory
                }
            }
        }]
    ))
    
    # Wait and exit (this is just a demonstration)
    time.sleep(5)
    log(f"[ENV Example] Environment check complete")