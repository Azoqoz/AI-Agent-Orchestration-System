from __future__ import annotations

import json
import os
import urllib.request
from typing import Any


class ProviderError(RuntimeError):
    def __init__(self, message: str, user_message: str | None = None) -> None:
        super().__init__(message)
        self.user_message = user_message or message


def _ollama_base_url() -> str:
    url = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
    return url.removesuffix("/api/generate")


def check_ollama_connection(timeout: float = 3) -> None:
    try:
        with urllib.request.urlopen(f"{_ollama_base_url()}/api/tags", timeout=timeout):
            return
    except Exception as exc:
        raise ProviderError(
            f"Ollama connection check failed: {exc}",
            "Could not connect to Ollama. Make sure Ollama is running locally.",
        ) from exc


def generate_text(
    provider: str,
    prompt: str,
    api_key: str | None = None,
    model: str | None = None,
    output_schema: dict[str, Any] | None = None,
) -> str:
    name = provider.lower(); key = api_key or _env_key(name)
    try:
        if name == "openai":
            if not key: raise ProviderError("OpenAI requires OPENAI_API_KEY or a session-only key")
            from openai import OpenAI
            response = OpenAI(api_key=key,timeout=30).responses.create(model=model or "gpt-4.1-mini",input=prompt)
            return response.output_text
        if name == "anthropic":
            if not key: raise ProviderError("Anthropic requires ANTHROPIC_API_KEY or a session-only key")
            from anthropic import Anthropic
            response=Anthropic(api_key=key,timeout=30).messages.create(model=model or "claude-3-5-haiku-latest",max_tokens=2500,messages=[{"role":"user","content":prompt}])
            return response.content[0].text
        if name == "gemini":
            if not key: raise ProviderError("Gemini requires GEMINI_API_KEY or a session-only key")
            from google import genai
            return genai.Client(api_key=key).models.generate_content(model=model or "gemini-2.0-flash",contents=prompt).text
        if name == "ollama":
            check_ollama_connection()
            body=json.dumps({
                "model": model or "llama3.2",
                "prompt": prompt,
                "stream": False,
                "format": output_schema or "json",
                "options": {"temperature": 0},
            }).encode()
            req=urllib.request.Request(f"{_ollama_base_url()}/api/generate",data=body,headers={"Content-Type":"application/json"})
            with urllib.request.urlopen(req,timeout=45) as response: return json.loads(response.read())["response"]
        raise ProviderError(f"Unsupported LLM provider: {provider}")
    except ProviderError: raise
    except ImportError as exc: raise ProviderError(f"The {provider} provider package is not installed") from exc
    except Exception as exc: raise ProviderError(f"{provider.title()} planning failed: {exc}") from exc


def _env_key(provider: str) -> str | None:
    return os.getenv({"openai":"OPENAI_API_KEY","anthropic":"ANTHROPIC_API_KEY","gemini":"GEMINI_API_KEY"}.get(provider,""))
