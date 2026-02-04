#!/usr/bin/env python3
"""
Model Provider Abstraction Layer

Supports both local (Ollama, vLLM) and cloud-based (Claude, GPT, Gemini) LLM providers.
Normalizes request/response handling across providers.
"""
from __future__ import annotations

import os
import time
import json
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
import requests


class ModelProvider(ABC):
    """Base class for all model providers."""

    @abstractmethod
    def generate(
        self,
        model: str,
        prompt: str,
        system: str,
        num_predict: int,
        temperature: float,
        timeout: int = 10,
        force_json: bool = False,
    ) -> str:
        """Generate text from the model. Returns raw text response."""
        pass


class OllamaProvider(ModelProvider):
    """Local Ollama or compatible endpoint (OpenAI-style API)."""

    def __init__(self, endpoint: str):
        """
        Args:
            endpoint: e.g. "http://127.0.0.1:11434/api/generate"
        """
        self.endpoint = endpoint.rstrip("/")

    def generate(
        self,
        model: str,
        prompt: str,
        system: str,
        num_predict: int,
        temperature: float,
        timeout: int = 10,
        force_json: bool = False,
    ) -> str:
        payload = {
            "model": model,
            "prompt": prompt,
            "system": system,
            "stream": False,
            "options": {
                "temperature": float(temperature),
                "num_predict": int(num_predict),
            },
        }

        if force_json:
            payload["format"] = "json"

        r = requests.post(
            self.endpoint,
            json=payload,
            timeout=(3, max(4, int(timeout))),
            headers={"Connection": "close"},
        )
        r.raise_for_status()

        out = (r.json().get("response") or "").strip()

        # Strip common wrappers
        out = out.replace("```json", "```").strip()
        if out.startswith("```"):
            out = out.strip("`").strip()

        return out


class AnthropicProvider(ModelProvider):
    """Anthropic Claude API provider."""

    def __init__(self, api_key: str):
        """
        Args:
            api_key: Claude API key
        """
        self.api_key = api_key
        self.base_url = "https://api.anthropic.com/v1"

    def generate(
        self,
        model: str,
        prompt: str,
        system: str,
        num_predict: int,
        temperature: float,
        timeout: int = 10,
        force_json: bool = False,
    ) -> str:
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        payload = {
            "model": model or "claude-3-5-sonnet-20241022",
            "max_tokens": int(num_predict),
            "temperature": float(temperature),
            "system": system,
            "messages": [
                {"role": "user", "content": prompt},
            ],
        }

        r = requests.post(
            f"{self.base_url}/messages",
            json=payload,
            headers=headers,
            timeout=(3, max(4, int(timeout))),
        )
        r.raise_for_status()

        data = r.json()
        out = ""

        if "content" in data and isinstance(data["content"], list):
            for block in data["content"]:
                if block.get("type") == "text":
                    out += block.get("text", "")

        out = out.strip()

        if force_json:
            out = out.replace("```json", "```").strip()
            if out.startswith("```"):
                out = out.strip("`").strip()

        return out


class OpenAIProvider(ModelProvider):
    """OpenAI GPT API provider."""

    def __init__(self, api_key: str):
        """
        Args:
            api_key: OpenAI API key
        """
        self.api_key = api_key
        self.base_url = "https://api.openai.com/v1"

    def generate(
        self,
        model: str,
        prompt: str,
        system: str,
        num_predict: int,
        temperature: float,
        timeout: int = 10,
        force_json: bool = False,
    ) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": model or "gpt-4",
            "max_tokens": int(num_predict),
            "temperature": float(temperature),
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        }

        if force_json:
            payload["response_format"] = {"type": "json_object"}

        r = requests.post(
            f"{self.base_url}/chat/completions",
            json=payload,
            headers=headers,
            timeout=(3, max(4, int(timeout))),
        )
        r.raise_for_status()

        data = r.json()
        out = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()

        return out


class GoogleProvider(ModelProvider):
    """Google Gemini API provider."""

    def __init__(self, api_key: str):
        """
        Args:
            api_key: Google API key for Generative AI
        """
        self.api_key = api_key
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/models"

    def generate(
        self,
        model: str,
        prompt: str,
        system: str,
        num_predict: int,
        temperature: float,
        timeout: int = 10,
        force_json: bool = False,
    ) -> str:
        model_id = model or "gemini-1.5-flash"

        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": f"{system}\n\n{prompt}",
                        }
                    ]
                }
            ],
            "generationConfig": {
                "maxOutputTokens": int(num_predict),
                "temperature": float(temperature),
            },
        }

        if force_json:
            payload["generationConfig"]["responseMimeType"] = "application/json"

        url = f"{self.base_url}/{model_id}:generateContent?key={self.api_key}"

        r = requests.post(
            url,
            json=payload,
            timeout=(3, max(4, int(timeout))),
        )
        r.raise_for_status()

        data = r.json()
        out = ""

        if "candidates" in data:
            for candidate in data["candidates"]:
                if "content" in candidate:
                    for part in candidate["content"].get("parts", []):
                        out += part.get("text", "")

        out = out.strip()

        if force_json:
            out = out.replace("```json", "```").strip()
            if out.startswith("```"):
                out = out.strip("`").strip()

        return out


def get_llm_provider(cfg: Dict[str, Any]) -> ModelProvider:
    """
    Factory function to instantiate the correct provider based on config.

    Config structure:
    {
        "llm": {
            "provider": "ollama" | "anthropic" | "openai" | "google",
            "endpoint": "http://...",  # for local providers
            "api_key_env": "ENV_VAR_NAME",  # for API providers
        }
    }

    Falls back to Ollama if llm.provider not specified (backward compatibility).
    """
    llm_cfg = cfg.get("llm") or {}

    if not isinstance(llm_cfg, dict):
        raise ValueError("llm config must be a dict")

    provider_type = (llm_cfg.get("provider") or "ollama").strip().lower()

    # Local providers
    if provider_type == "ollama":
        endpoint = (llm_cfg.get("endpoint") or "").strip()
        if not endpoint:
            endpoint = "http://127.0.0.1:11434/api/generate"
        return OllamaProvider(endpoint)

    # API-based providers
    elif provider_type == "anthropic":
        api_key_env = (llm_cfg.get("api_key_env") or "ANTHROPIC_API_KEY").strip()
        api_key = os.environ.get(api_key_env, "").strip()
        if not api_key:
            raise ValueError(
                f"Anthropic provider requires API key in env var: {api_key_env}"
            )
        return AnthropicProvider(api_key)

    elif provider_type == "openai":
        api_key_env = (llm_cfg.get("api_key_env") or "OPENAI_API_KEY").strip()
        api_key = os.environ.get(api_key_env, "").strip()
        if not api_key:
            raise ValueError(f"OpenAI provider requires API key in env var: {api_key_env}")
        return OpenAIProvider(api_key)

    elif provider_type == "google":
        api_key_env = (llm_cfg.get("api_key_env") or "GOOGLE_API_KEY").strip()
        api_key = os.environ.get(api_key_env, "").strip()
        if not api_key:
            raise ValueError(f"Google provider requires API key in env var: {api_key_env}")
        return GoogleProvider(api_key)

    else:
        raise ValueError(f"Unknown LLM provider: {provider_type}")


def log_provider_info(provider_type: str, model: str) -> str:
    """Generate a log-friendly string about the provider."""
    provider_display = {
        "ollama": "Ollama",
        "anthropic": "Claude (Anthropic)",
        "openai": "GPT (OpenAI)",
        "google": "Gemini (Google)",
    }
    return f"{provider_display.get(provider_type, provider_type)} [{model}]"
