#!/usr/bin/env python3
"""NOX Offline Teacher: independent local-model inference with NO PAID EXTERNAL API.

Supports already-downloaded GGUF through llama-cli and preinstalled Ollama models.
No arbitrary shell execution; no downloads, remote accounts or writes
to the NOX student model. Run on an isolated VM, not on the busy NOX A100 trainer.
"""
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

MAX_PROMPT = 6000
MAX_RESPONSE = 14000
LOCAL_MODEL_ROOTS = (
    Path("/opt/nox/teachers"), Path("/root/nox/teachers"), Path("/models")
)
RUN_PATH = "/usr/local/cuda/bin:/usr/local/bin:/usr/bin:/bin"


@dataclass(frozen=True)
class OfflineTeacher:
    name: str
    model_id: str
    model_card_url: str
    backend: str  # 'llama_cpp_cli' or 'ollama_cli'
    model_path: str = ""  # required for llama_cpp_cli
    approved_for_learning: bool = False


def _allowed_file(raw: str) -> bool:
    if not raw or not os.path.isabs(raw):
        return False
    try:
        p = Path(raw).resolve(strict=True)
        if not p.is_file() or p.suffix.lower() != ".gguf" or p.stat().st_size < 1024:
            return False
        return any(root == p.parent or root in p.parents for root in LOCAL_MODEL_ROOTS)
    except (OSError, ValueError):
        return False


def _installed_ollama(model: str) -> bool:
    try:
        result = subprocess.run(["ollama", "list"], capture_output=True, text=True,
                                timeout=5, env=_env())
        if result.returncode:
            return False
        # Ollama's 'NAME' column is the first token, so compare exact name.
        return model in {
            line.split()[0] for line in result.stdout.splitlines()[1:]
            if line.split()
        }
    except (OSError, subprocess.TimeoutExpired):
        return False


def _env() -> dict:
    return {
        "HOME": os.environ.get("HOME", "/root"),
        "PATH": RUN_PATH,
        "LC_ALL": "C.UTF-8",
        "OLLAMA_HOST": "127.0.0.1:11434",
        "NO_COLOR": "1"
    }


def infer_offline(teacher: OfflineTeacher, prompt: str, max_seconds: int = 75) -> dict:
    """Only textual evidence returned. This never updates teacher/NOX weights."""
    if teacher.backend not in ("llama_cpp_cli", "ollama_cli"):
        return {"status": "HOLD_OFFLINE_BACKEND", "teacher": teacher.name}
    if (not isinstance(prompt, str) or len(prompt) > MAX_PROMPT
            or not prompt.strip()):
        return {"status": "HOLD_PROMPT_LENGTH", "teacher": teacher.name}
    if not re.fullmatch(r"[A-Za-z0-9./:_-]{1,160}", teacher.model_id):
        return {"status": "HOLD_MODEL_ID", "teacher": teacher.name}
    if not teacher.model_card_url.startswith("https://huggingface.co/"):
        return {"status": "HOLD_MODEL_PROVENANCE", "teacher": teacher.name}
    max_seconds = max(5, min(180, int(max_seconds)))
    if teacher.backend == "llama_cpp_cli":
        if not _allowed_file(teacher.model_path):
            return {"status": "HOLD_GGUF_NOT_STAGED", "teacher": teacher.name}
        if not shutil.which("llama-cli", path=RUN_PATH):
            return {"status": "HOLD_LLAMA_CLI_MISSING", "teacher": teacher.name}
        command = ["llama-cli", "-m", teacher.model_path, "-p", prompt,
                   "-n", "768", "--temp", "0.25"]
        stdin = None
    else:
        if not shutil.which("ollama", path=RUN_PATH):
            return {"status": "HOLD_OLLAMA_NOT_INSTALLED", "teacher": teacher.name}
        if not _installed_ollama(teacher.model_id):
            # Never download a model implicitly or when the local model is absent.
            return {"status": "HOLD_OLLAMA_MODEL_NOT_PRESENT", "teacher": teacher.name}
        command = ["ollama", "run", teacher.model_id]
        stdin = prompt
    start = time.monotonic()
    try:
        proc = subprocess.run(command, input=stdin, capture_output=True, text=True,
                              timeout=max_seconds, env=_env(), check=False)
    except (OSError, subprocess.TimeoutExpired, UnicodeError):
        return {"status": "HOLD_OFFLINE_TIMEOUT", "teacher": teacher.name}
    if proc.returncode:
        return {"status": "HOLD_OFFLINE_EXIT", "teacher": teacher.name,
                "exit_code": proc.returncode}
    answer = proc.stdout.strip()
    if not answer or len(answer) > MAX_RESPONSE:
        return {"status": "HOLD_OFFLINE_EMPTY_OR_LONG", "teacher": teacher.name}
    return {
        "status": "MEASURED", "teacher": teacher.name,
        "model_id": teacher.model_id,
        "model_card_url": teacher.model_card_url,
        "answer": answer,
        "answer_sha256": hashlib.sha256(answer.encode()).hexdigest(),
        "latency_ms": round((time.monotonic() - start) * 1000),
        "approved_for_learning": teacher.approved_for_learning,
        "transport": "OFFLINE_VM_NO_EXTERNAL_API"
    }
