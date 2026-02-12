#!/usr/bin/env python3
"""
Voice Provider Abstraction Layer

Supports both local (Piper) and cloud-based (ElevenLabs, Google Cloud TTS, Azure) TTS providers.
Normalizes voice synthesis across providers.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Tuple
import requests
import numpy as np


class VoiceProvider(ABC):
    """Base class for all voice synthesis providers."""

    @abstractmethod
    def synthesize(self, voice_key: str, text: str, voice_map: Dict[str, str]) -> Tuple[np.ndarray, int]:
        """
        Synthesize speech for the given text.

        Args:
            voice_key: Character/voice identifier (e.g. "host", "skeptic")
            text: Text to synthesize
            voice_map: Dict mapping voice_key to voice config (path, ID, etc.)

        Returns:
            (audio_data: np.ndarray float32, sample_rate: int)
            audio_data should be mono or stereo (can reshape if needed).
        """
        pass


class PiperProvider(VoiceProvider):
    """Local Piper TTS (offline, requires binary + ONNX models)."""

    def __init__(self, piper_bin: str):
        """
        Args:
            piper_bin: Path to piper executable
        """
        self.piper_bin = piper_bin

    def synthesize(
        self, voice_key: str, text: str, voice_map: Dict[str, str]
    ) -> Tuple[np.ndarray, int]:
        """
        Use piper to generate WAV from text.
        Requires soundfile (sf) and numpy for loading.
        """
        import soundfile as sf

        if not self.piper_bin or not os.path.exists(self.piper_bin):
            raise RuntimeError(f"Piper binary not found: {self.piper_bin}")

        # Get voice model path
        voice_path = voice_map.get(voice_key) or voice_map.get("host")
        if not voice_path or not os.path.exists(voice_path):
            raise RuntimeError(f"Voice model not found for key={voice_key}: {voice_path}")

        # Generate temporary WAV file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav_path = f.name

        try:
            r = subprocess.run(
                [self.piper_bin, "-m", voice_path, "-f", wav_path],
                input=text,
                text=True,
                encoding="utf-8",
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=60,
            )

            if r.returncode != 0 or not os.path.exists(wav_path) or os.path.getsize(wav_path) <= 44:
                raise RuntimeError(f"Piper failed or produced invalid WAV: rc={r.returncode}")

            # Load WAV
            data, sr = sf.read(wav_path, dtype="float32")

            return data, int(sr)

        finally:
            try:
                os.remove(wav_path)
            except Exception:
                pass


class ElevenLabsProvider(VoiceProvider):
    """ElevenLabs API TTS provider."""

    def __init__(self, api_key: str):
        """
        Args:
            api_key: ElevenLabs API key
        """
        self.api_key = api_key
        self.base_url = "https://api.elevenlabs.io/v1"

    def synthesize(
        self, voice_key: str, text: str, voice_map: Dict[str, str]
    ) -> Tuple[np.ndarray, int]:
        """
        Call ElevenLabs API to generate speech.
        voice_map should contain voice_key -> voice_id mapping.
        """
        import soundfile as sf

        # Get voice ID from mapping
        voice_id = voice_map.get(voice_key) or voice_map.get("host")
        if not voice_id:
            raise ValueError(f"Voice ID not found for key={voice_key}")

        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
        }

        payload = {
            "text": text,
            "model_id": "eleven_monolingual_v1",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
            },
        }

        url = f"{self.base_url}/text-to-speech/{voice_id}"

        r = requests.post(url, json=payload, headers=headers, timeout=30)
        r.raise_for_status()

        audio_bytes = r.content

        # Load audio from bytes
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            temp_audio = f.name
            f.write(audio_bytes)

        try:
            data, sr = sf.read(temp_audio, dtype="float32")
            return data, int(sr)
        finally:
            try:
                os.remove(temp_audio)
            except Exception:
                pass


class GoogleCloudTTSProvider(VoiceProvider):
    """Google Cloud Text-to-Speech API provider."""

    def __init__(self, api_key: str):
        """
        Args:
            api_key: Google Cloud API key (TTS enabled)
        """
        self.api_key = api_key
        self.base_url = "https://texttospeech.googleapis.com/v1/text:synthesize"

    def synthesize(
        self, voice_key: str, text: str, voice_map: Dict[str, str]
    ) -> Tuple[np.ndarray, int]:
        """
        Call Google Cloud TTS API.
        voice_map should contain voice_key -> "en-US-Neural2-X" style voice name.
        """
        import soundfile as sf
        from pydub import AudioSegment
        import io

        # Get voice name
        voice_name = voice_map.get(voice_key) or voice_map.get("host")
        if not voice_name:
            voice_name = "en-US-Neural2-C"  # Default US female voice

        payload = {
            "input": {"text": text},
            "voice": {
                "languageCode": "en-US",
                "name": voice_name,
            },
            "audioConfig": {
                "audioEncoding": "MP3",
            },
        }

        params = {"key": self.api_key}

        r = requests.post(self.base_url, json=payload, params=params, timeout=30)
        r.raise_for_status()

        audio_content = r.json().get("audioContent", "")
        if not audio_content:
            raise RuntimeError("Google Cloud TTS returned empty audio")

        # Decode base64 audio
        import base64

        audio_bytes = base64.b64decode(audio_content)

        # Convert MP3 to WAV via pydub
        audio = AudioSegment.from_mp3(io.BytesIO(audio_bytes))

        # Convert to numpy array
        samples = np.array(audio.get_array_of_samples(), dtype=np.float32)
        samples = samples / (2**15)  # Normalize to [-1, 1]

        # Handle stereo -> mono if needed
        if audio.channels == 2:
            samples = samples.reshape((-1, 2))
            samples = samples.mean(axis=1)

        return samples, audio.frame_rate


class AzureSpeechProvider(VoiceProvider):
    """Azure Cognitive Services Speech synthesis provider."""

    def __init__(self, api_key: str, region: str):
        """
        Args:
            api_key: Azure Cognitive Services API key
            region: Azure region (e.g. "eastus")
        """
        self.api_key = api_key
        self.region = region
        self.base_url = f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"

    def synthesize(
        self, voice_key: str, text: str, voice_map: Dict[str, str]
    ) -> Tuple[np.ndarray, int]:
        """
        Call Azure Speech synthesis API.
        voice_map should contain voice_key -> "en-US-AriaNeural" style voice.
        """
        import soundfile as sf

        voice_name = voice_map.get(voice_key) or voice_map.get("host")
        if not voice_name:
            voice_name = "en-US-AriaNeural"

        # SSML format for Azure
        ssml = f"""<speak version='1.0' xml:lang='en-US'>
            <voice name='{voice_name}'>
                {text}
            </voice>
        </speak>"""

        headers = {
            "Ocp-Apim-Subscription-Key": self.api_key,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": "audio-16khz-32kbitrate-mono-mp3",
        }

        r = requests.post(self.base_url, data=ssml.encode("utf-8"), headers=headers, timeout=30)
        r.raise_for_status()

        audio_bytes = r.content

        # Convert MP3 to WAV
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            temp_audio = f.name
            f.write(audio_bytes)

        try:
            data, sr = sf.read(temp_audio, dtype="float32")
            return data, int(sr)
        finally:
            try:
                os.remove(temp_audio)
            except Exception:
                pass


def get_voice_provider(cfg: Dict[str, Any], audio_cfg: Optional[Dict[str, Any]] = None) -> VoiceProvider:
    """
    Factory function to instantiate the correct voice provider.

    Config structure:
    {
        "audio": {
            "voices_provider": "piper" | "elevenlabs" | "google" | "azure",
            "piper_bin": "/path/to/piper",  # for piper
            "api_key_env": "ENV_VAR_NAME",  # for API providers
            "region": "eastus",  # for azure
        }
    }

    Defaults to Piper if not specified (backward compatibility).
    """
    if audio_cfg is None:
        audio_cfg = cfg.get("audio") or {}

    if not isinstance(audio_cfg, dict):
        raise ValueError("audio config must be a dict")

    provider_type = (audio_cfg.get("voices_provider") or "piper").strip().lower()

    # Local provider
    if provider_type == "piper":
        piper_bin = (audio_cfg.get("piper_bin") or "").strip()
        if not piper_bin:
            # Try to auto-detect
            from runtime import _auto_detect_piper_bin
            piper_bin = _auto_detect_piper_bin()
        if not piper_bin:
            raise RuntimeError("Piper binary not found and could not auto-detect")
        return PiperProvider(piper_bin)

    # API-based providers
    elif provider_type == "elevenlabs":
        api_key_env = (audio_cfg.get("api_key_env") or "ELEVENLABS_API_KEY").strip()
        api_key = os.environ.get(api_key_env, "").strip()
        if not api_key:
            raise ValueError(
                f"ElevenLabs provider requires API key in env var: {api_key_env}"
            )
        return ElevenLabsProvider(api_key)

    elif provider_type == "google":
        api_key_env = (audio_cfg.get("api_key_env") or "GOOGLE_API_KEY").strip()
        api_key = os.environ.get(api_key_env, "").strip()
        if not api_key:
            raise ValueError(f"Google Cloud provider requires API key in env var: {api_key_env}")
        return GoogleCloudTTSProvider(api_key)

    elif provider_type == "azure":
        api_key_env = (audio_cfg.get("api_key_env") or "AZURE_SPEECH_KEY").strip()
        api_key = os.environ.get(api_key_env, "").strip()
        if not api_key:
            raise ValueError(f"Azure provider requires API key in env var: {api_key_env}")
        region = (audio_cfg.get("region") or "eastus").strip()
        return AzureSpeechProvider(api_key, region)

    else:
        raise ValueError(f"Unknown voice provider: {provider_type}")


def log_voice_provider_info(provider_type: str, voice_key: str) -> str:
    """Generate a log-friendly string about the voice provider."""
    provider_display = {
        "piper": "Piper (local)",
        "elevenlabs": "ElevenLabs",
        "google": "Google Cloud TTS",
        "azure": "Azure Speech",
    }
    return f"{provider_display.get(provider_type, provider_type)} [{voice_key}]"
