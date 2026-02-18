# Radio OS User Guide

## Introduction
Radio OS is a desktop-first, content-agnostic AI radio runtime. It functions as a "radio station in a box," where AI agents (Producers and Hosts) curate content from the web, mix it with music, and broadcast it using text-to-speech.

## Installation

### Prerequisites
- **Operating System**: Windows 10/11, macOS, or Linux.
- **Python**: Version 3.10 or higher.
- **FFmpeg**: Required for audio processing. Must be installed and added to your system's PATH.

### Quick Start (Windows)
1.  Navigate to the project root.
2.  Double-click `windows.bat` or run it from a terminal.
3.  The script will set up the virtual environment, install dependencies, and launch the application.

### Quick Start (macOS/Linux)
1.  Open a terminal in the project root.
2.  Make the script executable: `chmod +x mac.sh`
3.  Run the script: `./mac.sh`

### Manual Installation
If you prefer to set it up manually:

1.  **Create a Virtual Environment**:
    ```bash
    python -m venv radioenv
    ```
2.  **Activate the Environment**:
    - Windows: `radioenv\Scripts\activate`
    - macOS/Linux: `source radioenv/bin/activate`
3.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
4.  **Download Resources (Voices/Models)**:
    ```bash
    python setup.py
    ```
5.  **Launch the Shell**:
    ```bash
    python shell.py
    ```

## Usage

### The Shell
The Shell (`shell.py`) is the main desktop interface. It allows you to:
-   View available stations.
-   Launch a station.
-   Monitor station output (logs/transcripts).
-   Control playback (widgets).

### Creating a Station
Stations are self-contained folders located in the `stations/` directory.

1.  **Create a Folder**: Create a new directory under `stations/` (e.g., `stations/MyTechRadio`).
2.  **Create Manifest**: Copy `templates/default_manifest.yaml` to your new folder and rename it to `manifest.yaml`.
3.  **Configure**: Edit `manifest.yaml` to define your station's personality, feeds, and settings.

### Station Manifest Configuration
The `manifest.yaml` file is the heart of your station. Key sections include:

-   **identity**: Name, description, and genre of your station.
-   **llm**: Configuration for the Large Language Model.
    -   `provider`: `ollama`, `openai`, `anthropic`, `google`, etc.
    -   `model`: The specific model name (e.g., `gpt-4o`, `claude-3-5-sonnet`).
    -   `api_key_env`: The name of the environment variable containing your API key.
-   **audio**: Audio driver settings and voice provider selection.
    -   `voices_provider`: `piper` (local), `elevenlabs`, `azure`, `google`.
-   **voices**: Map station roles to voice IDs.
    -   `host`: The main voice.
    -   `producer`: The "voice in the ear" (internal logs).
-   **pacing**: Control how often the host speaks vs. playing music.
-   **feeds**: Enable or disable plugins (RSS, Reddit, etc.) and configure their sources.

## Providers & API Keys
Radio OS supports various AI providers. You should set your API keys as environment variables for security.

**Supported LLM Providers:**
-   Ollama (Local, Free)
-   OpenAI (GPT-4, etc.)
-   Anthropic (Claude)
-   Google (Gemini)

**Supported Voice Providers:**
-   Piper (Local, High Quality, Free)
-   ElevenLabs
-   Azure Speech
-   Google Cloud TTS

**Setting Environment Variables:**
You can set these in your OS, or pass them when running manually.
Examples:
-   `OPENAI_API_KEY`
-   `ELEVENLABS_API_KEY`
-   `ANTHROPIC_API_KEY`

## Plugin System
Plugins are located in the `plugins/` directory. They can:
-   **Fetch Content**: `rss.py`, `reddit.py`, `bluesky.py`, etc.
-   **Provide UI**: Add widgets to the shell window.

To enable a plugin for a station, add it to the `feeds` section of your `manifest.yaml`.

## Troubleshooting

-   **"FFmpeg not found"**: Ensure FFmpeg is installed and accessible in your terminal.
-   **No Sound**: Check your system volume and the `audio` configuration in the manifest.
-   **LLM Errors**: Check your API keys and ensure you have access to the selected model. If using Ollama, make sure the Ollama server is running (`ollama serve`).
-   **Station Crashes**: Check the logs in `stations/<YourStation>/runtime.log` for details.
