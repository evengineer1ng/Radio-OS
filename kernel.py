import yaml, os

def load_manifest(station_dir: str):
    path = os.path.join(station_dir, "manifest.yaml")
    try:
        with open(path, "r") as f:
            return yaml.safe_load(f)
    except Exception:
        return {}

def get_scheduler_quotas(manifest):
    return manifest.get("scheduler", {}).get("quotas", {})
