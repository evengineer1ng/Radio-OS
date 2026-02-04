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

    runtime = os.path.join(station_dir, "algofm.py")

    return subprocess.Popen(
        [sys.executable, runtime],
        cwd=station_dir,
        env=env
    )


if __name__ == "__main__":
    launch_station("algotradingfm")
