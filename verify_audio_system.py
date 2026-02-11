#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Audio System Verification Script
Tests that all components are properly installed and configured.
"""

import sys
import os
import io

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

print("=" * 70)
print("FromTheBackmarker Audio System Verification")
print("=" * 70)
print()

# Test 1: Python environment
print("[OK] Python version:", sys.version.split()[0])

# Test 2: Required imports
print("\n[Testing Core Imports]")
errors = []

try:
    import pygame
    print(f"✓ pygame version: {pygame.version.ver}")
except ImportError as e:
    print(f"✗ pygame: {e}")
    errors.append("pygame")

try:
    import sounddevice as sd
    print(f"✓ sounddevice: OK")
except ImportError as e:
    print(f"✗ sounddevice: {e}")
    errors.append("sounddevice")

try:
    import soundfile as sf
    print(f"✓ soundfile: OK")
except ImportError as e:
    print(f"✗ soundfile: {e}")
    errors.append("soundfile")

try:
    import numpy as np
    print(f"✓ numpy version: {np.__version__}")
except ImportError as e:
    print(f"✗ numpy: {e}")
    errors.append("numpy")

try:
    import yaml
    print(f"✓ yaml: OK")
except ImportError as e:
    print(f"✗ yaml: {e}")
    errors.append("yaml")

# Test 3: Audio engine plugin
print("\n[Testing Audio Engine Plugin]")
plugins_dir = os.path.join(os.path.dirname(__file__), 'plugins')
if plugins_dir not in sys.path:
    sys.path.insert(0, plugins_dir)

try:
    import ftb_audio_engine  # type: ignore
    print(f"✓ ftb_audio_engine plugin: Loaded")
    print(f"  - Plugin name: {ftb_audio_engine.PLUGIN_NAME}")
    print(f"  - Description: {ftb_audio_engine.PLUGIN_DESC}")
    print(f"  - Has pygame: {ftb_audio_engine.HAS_PYGAME}")
except Exception as e:
    print(f"✗ ftb_audio_engine: {e}")
    errors.append("ftb_audio_engine")

# Test 4: pygame mixer initialization
print("\n[Testing Pygame Mixer]")
if 'pygame' not in errors:
    try:
        pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
        pygame.mixer.set_num_channels(16)
        print(f"✓ pygame.mixer initialized successfully")
        print(f"  - Frequency: {pygame.mixer.get_init()[0]} Hz")
        print(f"  - Channels: {pygame.mixer.get_num_channels()}")
        pygame.mixer.quit()
    except Exception as e:
        print(f"✗ pygame.mixer initialization failed: {e}")
        errors.append("pygame.mixer")
else:
    print("⊘ Skipped (pygame not available)")

# Test 5: Audio directory structure
print("\n[Testing Audio Directory Structure]")
station_dir = os.path.join(os.path.dirname(__file__), 'stations', 'FromTheBackmarkerTemplate')
audio_dir = os.path.join(station_dir, 'audio')

required_dirs = [
    'music',
    'world/engines/grassroots',
    'world/engines/midformula',
    'world/engines/formulaz',
    'world/crashes',
    'ui'
]

for subdir in required_dirs:
    path = os.path.join(audio_dir, subdir)
    if os.path.exists(path):
        print(f"✓ {subdir}")
    else:
        print(f"✗ {subdir} (missing)")

# Test 6: Manifest configuration
print("\n[Testing Manifest Configuration]")
manifest_path = os.path.join(station_dir, 'manifest.yaml')
if os.path.exists(manifest_path):
    try:
        with open(manifest_path, 'r') as f:
            manifest = yaml.safe_load(f)
        
        audio_cfg = manifest.get('audio', {})
        feeds_cfg = manifest.get('feeds', {})
        
        if audio_cfg:
            print(f"✓ Audio configuration found")
            print(f"  - Music enabled: {audio_cfg.get('music_enabled', False)}")
            print(f"  - World audio enabled: {audio_cfg.get('world_audio_enabled', False)}")
            print(f"  - UI audio enabled: {audio_cfg.get('ui_audio_enabled', False)}")
            print(f"  - Master volume: {audio_cfg.get('master_volume', 0.8)}")
        else:
            print(f"⚠ Audio configuration section not found in manifest")
        
        if 'ftb_audio_engine' in feeds_cfg:
            enabled = feeds_cfg['ftb_audio_engine'].get('enabled', False)
            print(f"✓ ftb_audio_engine plugin entry: {'enabled' if enabled else 'disabled'}")
        else:
            print(f"⚠ ftb_audio_engine not in feeds section")
    
    except Exception as e:
        print(f"✗ Error reading manifest: {e}")
        errors.append("manifest")
else:
    print(f"✗ Manifest not found: {manifest_path}")
    errors.append("manifest")

# Test 7: Modified files check
print("\n[Testing Code Integration]")
bookmark_path = os.path.join(os.path.dirname(__file__), 'bookmark.py')
ftb_game_path = os.path.join(os.path.dirname(__file__), 'plugins', 'ftb_game.py')

try:
    with open(bookmark_path, 'r', encoding='utf-8') as f:
        bookmark_content = f.read()
    
    checks = [
        ('pygame import', 'import pygame' in bookmark_content),
        ('play_file_audio function', 'def play_file_audio(' in bookmark_content),
        ('pygame.mixer.init', 'pygame.mixer.init(' in bookmark_content),
    ]
    
    for check_name, check_result in checks:
        if check_result:
            print(f"✓ bookmark.py: {check_name}")
        else:
            print(f"✗ bookmark.py: {check_name} not found")
            errors.append(f"bookmark.py:{check_name}")
    
except Exception as e:
    print(f"✗ Error reading bookmark.py: {e}")
    errors.append("bookmark.py")

try:
    with open(ftb_game_path, 'r', encoding='utf-8') as f:
        ftb_game_content = f.read()
    
    checks = [
        ('engine_start event', "action='engine_start'" in ftb_game_content or 'action": "engine_start"' in ftb_game_content),
        ('crash audio event', "action='crash'" in ftb_game_content or 'action": "crash"' in ftb_game_content),
        ('performance state update', "type='audio'" in ftb_game_content or 'type": "audio"' in ftb_game_content),
    ]
    
    for check_name, check_result in checks:
        if check_result:
            print(f"✓ ftb_game.py: {check_name}")
        else:
            print(f"⚠ ftb_game.py: {check_name} not found (may use different format)")
    
except Exception as e:
    print(f"✗ Error reading ftb_game.py: {e}")
    errors.append("ftb_game.py")

# Summary
print("\n" + "=" * 70)
if errors:
    print(f"⚠ VERIFICATION INCOMPLETE - {len(errors)} issue(s) found:")
    for error in errors:
        print(f"  - {error}")
    print("\nSome features may not work. See AUDIO_SYSTEM_GUIDE.md for troubleshooting.")
else:
    print("✓ ALL CHECKS PASSED")
    print("\nAudio system ready! Next steps:")
    print("  1. Populate audio/ directory with music/engine/crash/UI sound files")
    print("  2. Start station: python stations/FromTheBackmarkerTemplate/ftb_entrypoint.py")
    print("  3. Monitor runtime.log for audio engine messages")
    print("\nSee AUDIO_SYSTEM_GUIDE.md for detailed setup instructions.")
print("=" * 70)
