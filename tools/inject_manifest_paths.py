#!/usr/bin/env python3
"""
Manifest Path Injection Utility
Replaces placeholder paths in station manifests with actual system paths
Called during first-run setup to configure Piper and voice paths
"""
import os
import sys
import yaml
import argparse
from pathlib import Path


def inject_paths_into_manifest(manifest_path: str, piper_bin: str, voices_dir: str) -> bool:
    """
    Replace placeholder paths in a manifest file with actual paths.
    
    Args:
        manifest_path: Path to station manifest.yaml file
        piper_bin: Absolute path to piper binary/executable
        voices_dir: Absolute path to voices directory
        
    Returns:
        True if successful, False on error
    """
    try:
        # Read manifest
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = yaml.safe_load(f)
        
        if not manifest:
            print(f"[!] Empty or invalid manifest: {manifest_path}")
            return False
        
        # Track if we made changes
        changed = False
        
        # Inject piper_bin path
        if 'audio' in manifest and 'piper_bin' in manifest['audio']:
            current = manifest['audio']['piper_bin']
            if '{PIPER_BIN_PATH}' in str(current):
                manifest['audio']['piper_bin'] = piper_bin
                changed = True
                print(f"  [+] Injected piper_bin: {piper_bin}")
        
        # Inject voice paths
        if 'voices' in manifest:
            for voice_key, voice_path in manifest['voices'].items():
                if voice_path and '{VOICES_DIR}' in str(voice_path):
                    # Extract filename from placeholder
                    filename = voice_path.replace('{VOICES_DIR}/', '')
                    actual_path = os.path.join(voices_dir, filename)
                    manifest['voices'][voice_key] = actual_path
                    changed = True
                    print(f"  [+] Injected voice '{voice_key}': {filename}")
        
        # Write back if changed
        if changed:
            # Atomic write: write to temp file then replace
            temp_path = manifest_path + '.tmp'
            with open(temp_path, 'w', encoding='utf-8') as f:
                yaml.dump(manifest, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
            
            os.replace(temp_path, manifest_path)
            print(f"[✓] Updated: {manifest_path}")
            return True
        else:
            print(f"[·] No changes needed: {manifest_path}")
            return True
            
    except Exception as e:
        print(f"[✗] Error processing {manifest_path}: {e}")
        return False


def inject_all_stations(stations_dir: str, piper_bin: str, voices_dir: str, exclude: list = None) -> tuple:
    """
    Process all station manifests in the stations directory.
    
    Args:
        stations_dir: Path to stations/ directory
        piper_bin: Absolute path to piper binary
        voices_dir: Absolute path to voices directory
        exclude: List of station IDs to skip (e.g., ['algotradingfm'])
        
    Returns:
        Tuple of (success_count, total_count)
    """
    exclude = exclude or []
    success_count = 0
    total_count = 0
    
    print(f"\n[*] Scanning stations directory: {stations_dir}")
    print(f"[*] Piper binary: {piper_bin}")
    print(f"[*] Voices directory: {voices_dir}")
    
    if exclude:
        print(f"[*] Excluding: {', '.join(exclude)}")
    
    print()
    
    # Find all station manifests
    stations_path = Path(stations_dir)
    if not stations_path.exists():
        print(f"[!] Stations directory not found: {stations_dir}")
        return (0, 0)
    
    for station_dir in stations_path.iterdir():
        if not station_dir.is_dir():
            continue
        
        station_id = station_dir.name
        
        # Skip excluded stations
        if station_id in exclude:
            print(f"[·] Skipping excluded station: {station_id}")
            continue
        
        # Look for manifest.yaml
        manifest_path = station_dir / 'manifest.yaml'
        if not manifest_path.exists():
            print(f"[·] No manifest found: {station_id}")
            continue
        
        print(f"[*] Processing: {station_id}")
        total_count += 1
        
        if inject_paths_into_manifest(str(manifest_path), piper_bin, voices_dir):
            success_count += 1
        
        print()
    
    return (success_count, total_count)


def main():
    parser = argparse.ArgumentParser(
        description='Inject system paths into Radio OS station manifests'
    )
    parser.add_argument(
        '--stations-dir',
        default='stations',
        help='Path to stations directory (default: stations)'
    )
    parser.add_argument(
        '--piper-bin',
        required=True,
        help='Absolute path to piper binary/executable'
    )
    parser.add_argument(
        '--voices-dir',
        required=True,
        help='Absolute path to voices directory'
    )
    parser.add_argument(
        '--exclude',
        nargs='+',
        default=['algotradingfm'],
        help='Station IDs to exclude (default: algotradingfm)'
    )
    parser.add_argument(
        '--single',
        help='Process only a single station manifest (path to manifest.yaml)'
    )
    
    args = parser.parse_args()
    
    # Validate inputs
    if not os.path.exists(args.piper_bin):
        print(f"[!] Piper binary not found: {args.piper_bin}")
        print(f"[!] Please ensure Piper is installed correctly")
        return 1
    
    if not os.path.exists(args.voices_dir):
        print(f"[!] Voices directory not found: {args.voices_dir}")
        print(f"[!] Please ensure voice models are downloaded")
        return 1
    
    # Process single manifest or all stations
    if args.single:
        print(f"[*] Processing single manifest: {args.single}")
        if inject_paths_into_manifest(args.single, args.piper_bin, args.voices_dir):
            print("\n[✓] Manifest injection complete!")
            return 0
        else:
            print("\n[✗] Manifest injection failed!")
            return 1
    else:
        success, total = inject_all_stations(
            args.stations_dir,
            args.piper_bin,
            args.voices_dir,
            args.exclude
        )
        
        print("=" * 50)
        print(f"[✓] Injection complete: {success}/{total} manifests updated")
        
        if success < total:
            print(f"[!] {total - success} manifest(s) failed - check errors above")
            return 1
        
        return 0


if __name__ == '__main__':
    sys.exit(main())
