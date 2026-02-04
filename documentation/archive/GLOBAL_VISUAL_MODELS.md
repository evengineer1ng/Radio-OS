# Global Visual Models Settings

A new **Visual Models** tab has been added to the shell's global settings, allowing centralized configuration of vision models for the RadioOS ecosystem.

## Overview

Instead of configuring vision models per-station, you can now set global defaults in the shell's global settings. Stations will automatically reference these configurations via environment variables.

## Storage Location

Global settings are stored in a platform-specific location:

- **Windows**: `%APPDATA%\RadioOS\config.json`
- **Mac/Linux**: `~/.radioOS/config.json`

The directory is created automatically on first use.

## Configuration Options

### Model Type
Choose between two approaches:

1. **Local Model** — Use a locally-hosted vision model via Ollama, LLaVA, or similar
   - Requires a running local service (e.g., `ollama serve`)
   - No API keys or internet required
   - Example endpoint: `http://localhost:11434` or model name `llava:latest`

2. **API-based Model** — Use a commercial vision API
   - Requires API credentials
   - Examples: OpenAI (GPT-4-Vision), Claude (Anthropic), Google Vision, custom endpoints

### Local Model Settings

- **Model Name / Endpoint**: The model identifier or service endpoint
  - Examples: `llava:latest`, `http://localhost:11434`, `ollama-local:8000`

### API Model Settings

- **API Provider**: Dropdown selector (openai, anthropic, google, custom)
- **Model Name**: The specific vision model to use
  - OpenAI example: `gpt-4-vision` or `gpt-4o`
  - Anthropic example: `claude-3-5-sonnet-20241022`
  - Google example: `gemini-1.5-pro`
- **API Key**: Your authentication token (masked in UI)
- **API Endpoint** (optional): Custom endpoint URL if not using standard provider endpoints

### Vision Processing Options

- **Max Image Size (width)**: Resize images to this width before sending to model (default: 1024)
  - Larger = more detail but slower and more expensive
  - Smaller = faster but may lose detail
- **Image Quality (1-100)**: JPEG compression level (default: 85)
  - Higher = better quality but larger file size
  - Lower = smaller but may lose visual fidelity

## Usage in Plugins

Plugins can access the global visual model config via the `your_runtime` shim:

```python
import your_runtime as rt

# Get visual model configuration
config = rt.get_visual_model_config()

# Access config fields
model_type = config["model_type"]  # "local" or "api"
if model_type == "local":
    endpoint = config["local_model"]
else:
    provider = config["api_provider"]
    api_key = config["api_key"]
    model = config["api_model"]
    api_endpoint = config["api_endpoint"]

max_size = config["max_image_size"]  # int
quality = config["image_quality"]     # int
```

## Environment Variables

When a station is launched, the global visual model config is injected via environment variables:

- `VISUAL_MODEL_TYPE` — "local" or "api"
- `VISUAL_MODEL_LOCAL` — Local model name/endpoint
- `VISUAL_MODEL_API_PROVIDER` — API provider name
- `VISUAL_MODEL_API_MODEL` — API model identifier
- `VISUAL_MODEL_API_KEY` — API authentication key
- `VISUAL_MODEL_API_ENDPOINT` — Custom API endpoint (if applicable)
- `VISUAL_MODEL_MAX_IMAGE_SIZE` — Max image width (string)
- `VISUAL_MODEL_IMAGE_QUALITY` — Compression quality (string)

These are set in `launcher.py` and accessible via `os.getenv()` in station processes.

## Example: Using with visual_reader Plugin

Once the `visual_reader` plugin is built, it will automatically use the global visual model configuration:

```python
# In visual_reader.py plugin
import your_runtime as rt

config = rt.get_visual_model_config()

if config["model_type"] == "local":
    # Connect to local Ollama/LLaVA instance
    client = OllamaClient(config["local_model"])
else:
    # Use API provider
    client = APIClient(
        provider=config["api_provider"],
        api_key=config["api_key"],
        model=config["api_model"],
        endpoint=config["api_endpoint"]
    )

# Screenshot interpretation loop uses this client...
```

## How to Access Settings

1. Launch the RadioOS shell: `python shell.py`
2. Click **Settings** (gear icon or menu)
3. Click the **Visual Models** tab
4. Configure your preferred model and options
5. Click **Save Settings**
6. Settings persist across shell restarts and are available to all stations

## Platform Notes

### Windows
- Settings stored in `%APPDATA%\RadioOS\config.json`
- Use `\\localhost` or IP addresses for local service endpoints

### Mac
- Settings stored in `~/.radioOS/config.json`
- Use `localhost` or IP addresses for local service endpoints

## Security Notes

- API keys are stored in plain text in the config file. 
- Consider filesystem permissions: `chmod 600 ~/.radioOS/config.json` on Mac/Linux
- On Windows, ensure the `RadioOS` folder has restricted permissions
- **Do not commit the config file to version control**

## Troubleshooting

### Settings not persisting?
- Check that the config directory exists and is writable
- Verify the JSON file syntax (open in a text editor)
- Look for error messages in the shell console

### Plugin not seeing settings?
- Ensure the station was launched **after** configuring global settings
- Check that environment variables are set: `echo $VISUAL_MODEL_TYPE` (Mac/Linux) or `echo %VISUAL_MODEL_TYPE%` (Windows)
- Verify the config structure in the global config file

### Connection errors to local model?
- Ensure Ollama or your local service is running
- Check the endpoint URL (e.g., `http://localhost:11434`)
- Test connectivity: `curl http://localhost:11434/api/tags` (for Ollama)

