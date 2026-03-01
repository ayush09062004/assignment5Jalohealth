"""
Groq API client wrapper.

Free tier: https://console.groq.com
- No credit card required
- Generous rate limits (up to 14,400 requests/day on free plan)
- Uses llama-3.3-70b-versatile — very capable for structured extraction

Get your free key at: https://console.groq.com/keys
"""

import json
import os
import re
from typing import Optional


def _get_client():
    """Lazy-import groq and build client."""
    try:
        from groq import Groq
    except ImportError:
        raise ImportError(
            "groq package not installed. Run: pip install groq"
        )
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set.\n"
            "Get your FREE key at https://console.groq.com/keys\n"
            "Then: export GROQ_API_KEY='gsk_...'"
        )
    return Groq(api_key=api_key)


# Default model — free, fast, very capable
DEFAULT_MODEL = "llama-3.3-70b-versatile"


def chat(
    prompt: str,
    system: str = "You are a helpful assistant. Always respond with valid JSON when asked.",
    model: str = DEFAULT_MODEL,
    max_tokens: int = 2048,
    temperature: float = 0.1,   # low temp for structured extraction
) -> str:
    """Send a single message to Groq and return the text response."""
    client = _get_client()
    response = client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    )
    return response.choices[0].message.content.strip()


def chat_json(
    prompt: str,
    system: str = "You are a helpful assistant. Respond ONLY with valid JSON — no markdown, no explanation.",
    model: str = DEFAULT_MODEL,
    max_tokens: int = 2048,
) -> dict | list:
    """Call Groq and parse JSON from the response."""
    raw = chat(prompt, system=system, model=model, max_tokens=max_tokens)

    # Strip markdown code fences if the model wraps output
    raw = re.sub(r"^```(?:json)?\s*\n?", "", raw, flags=re.MULTILINE)
    raw = re.sub(r"\n?```\s*$", "", raw, flags=re.MULTILINE)
    raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Last resort: extract first JSON object or array
        m = re.search(r"(\{.*\}|\[.*\])", raw, re.DOTALL)
        if m:
            return json.loads(m.group(1))
        raise ValueError(f"Could not parse JSON from Groq response:\n{raw[:400]}")
