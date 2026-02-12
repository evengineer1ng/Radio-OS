#!/usr/bin/env python3
"""
Demo script to show how to easily access Radio OS environment variables.

This script demonstrates how environment variables set in the Shell Settings
are automatically available to stations and plugins.
"""

import os

# Radio OS environment variables that can be configured in Shell Settings
radio_env_vars = [
    "RADIO_OS_ROOT",
    "RADIO_OS_PLUGINS", 
    "RADIO_OS_VOICES",
    "CONTEXT_MODEL",
    "HOST_MODEL",
    "OLLAMA_ENDPOINT",
    "PIPER_BIN",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "STATION_DIR",
    "STATION_DB_PATH",
    "STATION_MEMORY_PATH"
]

def show_environment():
    """Show current Radio OS environment variables."""
    print("="*60)
    print("Radio OS Environment Variables")
    print("="*60)
    print()
    
    for var in radio_env_vars:
        value = os.getenv(var)
        if value:
            # Hide sensitive values
            if "API_KEY" in var or "TOKEN" in var:
                display_value = f"{value[:8]}..." if len(value) > 8 else "***"
            else:
                display_value = value
            print(f"{var:20} = {display_value}")
        else:
            print(f"{var:20} = (not set)")
    
    print()
    print("Configuration:")
    print("- Set these in Radio OS Shell > Settings > Environment")
    print("- Changes apply to newly launched stations")
    print("- Station-specific vars (STATION_*) are set automatically")

if __name__ == "__main__":
    show_environment()