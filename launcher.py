import subprocess, os, sys, yaml

BASE_DIR = os.path.dirname(__file__)

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

    runtime = os.path.join(station_dir, "algofm.py")

    return subprocess.Popen(
        [sys.executable, runtime],
        cwd=station_dir,
        env=env
    )


if __name__ == "__main__":
    launch_station("algotradingfm")
