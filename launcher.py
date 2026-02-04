import subprocess, os, sys, yaml, json

BASE_DIR = os.path.dirname(__file__)

def get_global_config_path() -> str:
    """Return path to global RadioOS settings file."""
    if os.name == "nt":
        # Windows: %APPDATA%\RadioOS\config.json
        appdata = os.getenv("APPDATA", os.path.expanduser("~"))
        cfg_dir = os.path.join(appdata, "RadioOS")
    else:
        # Mac/Linux: ~/.radioOS/config.json
        cfg_dir = os.path.expanduser("~/.radioOS")
    return os.path.join(cfg_dir, "config.json")

def get_global_config() -> dict:
    """Load global settings (returns empty dict if not exists)."""
    path = get_global_config_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def launch_station(station_id: str):

    station_dir = os.path.join(BASE_DIR, "stations", station_id)
    manifest_path = os.path.join(station_dir, "manifest.yaml")

    with open(manifest_path, "r") as f:
        cfg = yaml.safe_load(f)

    env = os.environ.copy()

    # Core injected paths
    env["STATION_DIR"] = station_dir
    env["STATION_DB_PATH"] = os.path.join(station_dir, cfg["paths"]["db"])
    env["STATION_MEMORY_PATH"] = os.path.join(station_dir, cfg["paths"]["memory"])

    # Models
    env["CONTEXT_MODEL"] = cfg["models"]["producer_model"]
    env["HOST_MODEL"] = cfg["models"]["host_model"]

    # Global resources
    env["RADIO_OS_ROOT"] = BASE_DIR
    env["RADIO_OS_VOICES"] = os.path.join(BASE_DIR, "voices")
    env["RADIO_OS_PLUGINS"] = os.path.join(BASE_DIR, "plugins")

    # =====================================================
    # Multi-Provider: Pass API credentials via env vars
    # =====================================================
    
    # LLM API key (if configured in manifest or env)
    llm_cfg = cfg.get("llm", {})
    if isinstance(llm_cfg, dict):
        api_key_env = (llm_cfg.get("api_key_env") or "").strip()
        if api_key_env:
            # Check if already in env, else try to pick up from parent process
            if api_key_env not in env:
                # Optionally log this, but don't fail
                pass
    
    # Voice API key (if configured in manifest or env)
    audio_cfg = cfg.get("audio", {})
    if isinstance(audio_cfg, dict):
        api_key_env = (audio_cfg.get("api_key_env") or "").strip()
        if api_key_env:
            # Check if already in env
            if api_key_env not in env:
                pass

    # =====================================================
    # Global Visual Model Configuration
    # =====================================================
    global_cfg = get_global_config()
    visual_cfg = global_cfg.get("visual_models", {})
    
    # Merge with station manifest configuration (manifest takes precedence)
    if "visual_models" in cfg:
        visual_cfg.update(cfg["visual_models"])

    if visual_cfg:
        env["VISUAL_MODEL_TYPE"] = str(visual_cfg.get("model_type", "local"))
        env["VISUAL_MODEL_LOCAL"] = str(visual_cfg.get("local_model", "llava:latest"))
        env["VISUAL_MODEL_API_PROVIDER"] = str(visual_cfg.get("api_provider", ""))
        env["VISUAL_MODEL_API_MODEL"] = str(visual_cfg.get("api_model", ""))
        env["VISUAL_MODEL_API_KEY"] = str(visual_cfg.get("api_key", ""))
        env["VISUAL_MODEL_API_ENDPOINT"] = str(visual_cfg.get("api_endpoint", ""))
        env["VISUAL_MODEL_MAX_IMAGE_SIZE"] = str(visual_cfg.get("max_image_size", "1024"))
        env["VISUAL_MODEL_IMAGE_QUALITY"] = str(visual_cfg.get("image_quality", "85"))

    runtime = os.path.join(BASE_DIR, "runtime.py")

    return subprocess.Popen(
        [sys.executable, runtime],
        cwd=station_dir,
        env=env
    )


if __name__ == "__main__":
    launch_station("algotradingfm")
