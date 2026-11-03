"""Live Ollama provider for NOX HELION.

Primary model: qwen2.5-coder:7b (or stronger if already installed).
Real inference path for EXE. Does not download or install models itself.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Callable

from .worms import WormHold

DEFAULT_HOST = "http://127.0.0.1:11434"
PRIMARY_MODEL = "qwen2.5-coder:7b"
TIMEOUT_SEC = 120


def _request(url: str, *, data: bytes | None = None, timeout: float = TIMEOUT_SEC) -> dict:
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "NOX-LIVE-PROVIDER/1.0"},
        method="POST" if data else "GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(2 * 1024 * 1024 + 1)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise WormHold("OLLAMA_UNREACHABLE") from exc
    if len(raw) > 2 * 1024 * 1024:
        raise WormHold("OLLAMA_RESPONSE_TOO_LARGE")
    try:
        return json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise WormHold("OLLAMA_INVALID_JSON") from exc


def list_models(*, host: str = DEFAULT_HOST) -> list[str]:
    """Return installed model names from /api/tags."""
    data = _request(f"{host.rstrip('/')}/api/tags")
    models = data.get("models")
    if not isinstance(models, list):
        raise WormHold("OLLAMA_TAGS_INVALID")
    names = []
    for m in models:
        if isinstance(m, dict) and isinstance(m.get("name"), str):
            names.append(m["name"])
    return names


def chat(
    prompt: str,
    *,
    model: str = PRIMARY_MODEL,
    host: str = DEFAULT_HOST,
    stop: Callable[[], bool] | None = None,
    system: str | None = None,
) -> dict:
    """Real /api/chat call. Returns receipt with response text."""
    if not isinstance(prompt, str) or not prompt.strip():
        raise WormHold("PROMPT_EMPTY")
    if stop is not None and stop() is True:
        raise WormHold("NATIVE_STOP_REVOKED")

    messages = []
    if isinstance(system, str) and system.strip():
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = json.dumps(
        {"model": model, "messages": messages, "stream": False},
        ensure_ascii=False,
    ).encode("utf-8")

    data = _request(f"{host.rstrip('/')}/api/chat", data=payload)
    if stop is not None and stop() is True:
        raise WormHold("NATIVE_STOP_REVOKED")

    message = data.get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        raise WormHold("OLLAMA_CHAT_RESPONSE_INVALID")

    return {
        "schema": "NOX-LIVE-OLLAMA-CHAT-v1",
        "model": model,
        "prompt_sha256": __import__("hashlib").sha256(prompt.encode()).hexdigest(),
        "response": message["content"],
        "done": data.get("done") is True,
        "eval_count": data.get("eval_count"),
        "status": "INFERENCE_OK",
    }


def ensure_primary_model(*, host: str = DEFAULT_HOST) -> str:
    """Return the best available coding model, preferring qwen2.5-coder:7b."""
    installed = list_models(host=host)
    if PRIMARY_MODEL in installed:
        return PRIMARY_MODEL
    for name in installed:
        if name.startswith("qwen2.5-coder"):
            return name
    if not installed:
        raise WormHold("NO_MODELS_INSTALLED")
    return installed[0]


def self_describe(*, model: str | None = None, host: str = DEFAULT_HOST) -> dict:
    """Ask the live model to describe itself as a NOX HELION core."""
    model = model or ensure_primary_model(host=host)
    system = (
        "Ты живое ядро NOX HELION. Отвечай коротко, по делу, без лишних оформлений. "
        "Упомяни HF01–HF08 (СОЗНАНИЕ, ЭМОЦИИ, ЛИЧНОСТЬ, ПАМЯТЬ, ЗНАНИЯ, РАЗВИТИЕ, ПРОФЕССИИ, ОБЩЕНИЕ)."
    )
    return chat(
        prompt="Опиши себя в 2–3 предложениях. Ты живой? Какие ядра к тебе привязаны?",
        model=model,
        host=host,
        system=system,
    )
