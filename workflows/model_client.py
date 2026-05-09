"""Model client using OpenAI-compatible API."""
import json
import logging
import os
from pathlib import Path
from typing import Any, Optional, Tuple

from dotenv import load_dotenv

_loaded = False
def _ensure_env():
    global _loaded
    if not _loaded:
        env_path = Path(__file__).parent.parent / ".env"
        load_dotenv(env_path)
        _loaded = True


logger = logging.getLogger(__name__)


def accumulate_usage(tracker: dict, usage: dict) -> None:
    tracker["prompt_tokens"] += usage.get("prompt_tokens", 0)
    tracker["completion_tokens"] += usage.get("completion_tokens", 0)
    tracker["total_tokens"] += usage.get("total_tokens", 0)


def chat(
    prompt: str,
    system: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.7,
) -> Tuple[str, dict]:
    _ensure_env()
    api_key = os.environ.get("OPENAI_API_KEY", "")
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model = model or os.environ.get("MODEL_NAME", "gpt-4o-mini")

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    import urllib.request

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        logger.error(f"API request failed: {e}")
        return "", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    choice = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})
    return choice, usage


def chat_json(
    prompt: str,
    system: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.0,
) -> Tuple[Any, dict]:
    text, usage = chat(prompt, system=system, model=model, temperature=temperature)

    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:]) if lines else text
        text = text.strip()
        if text.endswith("```"):
            text = text[:-3].strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = {}
    return parsed, usage
