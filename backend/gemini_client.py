"""
Shared Gemini client — lazy-initialized so missing API key doesn't crash on import.
"""
from __future__ import annotations
from typing import Optional

_client = None


def get_client():
    """Get or create the shared genai Client."""
    global _client
    if _client is None:
        from google import genai
        from config import GOOGLE_API_KEY
        if not GOOGLE_API_KEY:
            raise ValueError("GOOGLE_API_KEY is not set. Please set it in backend/.env")
        _client = genai.Client(api_key=GOOGLE_API_KEY)
    return _client
