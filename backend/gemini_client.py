"""
Shared LLM client — supports both Google Gemini and Ollama backends.
Switch via LLM_BACKEND env var: "gemini" (default) or "ollama".

All agents call call_with_retry() and get back an object with a .text property —
the backend routing is invisible to them.
"""
from __future__ import annotations
import json
import re
import time

import httpx

# ── Gemini lazy client ─────────────────────────────────────────────────────

_gemini_client = None


def get_client():
    """Get or create the shared Gemini genai Client (only used in Gemini mode)."""
    global _gemini_client
    if _gemini_client is None:
        from google import genai
        from config import GOOGLE_API_KEY
        if not GOOGLE_API_KEY:
            raise ValueError(
                "GOOGLE_API_KEY is not set. Please set it in backend/.env "
                "or switch to Ollama with LLM_BACKEND=ollama"
            )
        _gemini_client = genai.Client(api_key=GOOGLE_API_KEY)
    return _gemini_client


# ── Ollama backend ─────────────────────────────────────────────────────────

class _OllamaResponse:
    """Wraps Ollama response to match the .text interface Gemini returns."""
    def __init__(self, text: str):
        self.text = text


def _call_ollama(system: str, user_content: str, temperature: float = 0.2) -> str:
    """POST to Ollama /api/chat and return the response content string."""
    from config import OLLAMA_BASE_URL, OLLAMA_MODEL

    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
        "stream": False,
        "format": "json",          # forces JSON output mode
        "options": {
            "temperature": temperature,
            "num_predict": 4096,   # max tokens
        },
    }

    try:
        with httpx.Client(timeout=300) as client:
            resp = client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["message"]["content"]
    except httpx.ConnectError:
        raise RuntimeError(
            f"Cannot connect to Ollama at {OLLAMA_BASE_URL}. "
            "Make sure Ollama is running: run 'ollama serve' in a terminal."
        )
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"Ollama API error: {e.response.status_code} — {e.response.text}")


# ── Unified entry point ────────────────────────────────────────────────────

def call_with_retry(model: str, contents: str, config, max_retries: int = 3):
    """
    Unified LLM call — routes to Gemini or Ollama based on LLM_BACKEND.
    Always returns an object with a .text property.
    Agents call this exactly as before — zero agent-side changes needed.
    """
    from config import LLM_BACKEND

    # ── Ollama path ──────────────────────────────────────────────────────
    if LLM_BACKEND == "ollama":
        system = getattr(config, "system_instruction", "") or ""
        temperature = float(getattr(config, "temperature", 0.2) or 0.2)
        text = _call_ollama(system, contents, temperature)
        return _OllamaResponse(text)

    # ── Gemini path with 429 retry backoff ───────────────────────────────
    default_delay = 35  # seconds

    for attempt in range(max_retries + 1):
        try:
            return get_client().models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
        except Exception as e:
            err_str = str(e)
            is_rate_limit = "429" in err_str or "RESOURCE_EXHAUSTED" in err_str

            if not is_rate_limit:
                raise

            if attempt == max_retries:
                raise

            # Extract suggested retry delay from Gemini error message
            match = re.search(r"retry[_ ]in[_ ](\d+(?:\.\d+)?)", err_str, re.IGNORECASE)
            delay = float(match.group(1)) + 3 if match else default_delay * (attempt + 1)
            delay = min(delay, 120)

            print(f"[Rate limit 429] Waiting {delay:.0f}s before retry {attempt + 1}/{max_retries}...")
            time.sleep(delay)
