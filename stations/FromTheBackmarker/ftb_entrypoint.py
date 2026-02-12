#!/usr/bin/env python3
"""
From the Backmarker - Station Entrypoint

This entrypoint imports and runs bookmark.py as the engine.
The meta plugin system will load the 'from_the_backmarker' meta plugin
based on the manifest.yaml configuration.
"""

import sys
import os

# Add parent directory to path to import bookmark
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Import bookmark as the engine
import bookmark

if __name__ == "__main__":
    # Run bookmark.py main loop
    # It will automatically:
    # 1. Load manifest.yaml
    # 2. Detect meta_plugin: "from_the_backmarker"
    # 3. Load ftb_game plugin as a feed
    # 4. Start simulation
    bookmark.main()
