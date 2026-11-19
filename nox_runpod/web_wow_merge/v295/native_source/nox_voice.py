# -*- coding: utf-8 -*-
"""Голосовой режим: CPU-лёгкий TTS с разрешительной лицензией.

Официальный Kokoro-82M — Apache-2.0, но без русского (языки: en, es, fr, hi, it, ja, pt-BR, zh).
Порт kokoro-ru несёт веса OpenRAIL — не берём автоматически.
Если владелец положит локальный пакет с Apache/MIT/OFL и явным ru в C:\\NOX\\voice\\kokoro — можно включить.
Иначе — голоса Windows SAPI (локально). Нет подходящего RU-голоса — честный HOLD.
Никакого скрейпинга облачных TTS и загрузок >100 МБ без Approve.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

MSK = timezone(timedelta(hours=3))
PERMISSIVE = {"apache-2.0", "apache 2.0", "apache2", "mit", "bsd-2-clause", "bsd-3-clause", "isc", "cc0", "ofl", "unlicense"}


def _now() -> str:
    return datetime.now(MSK).replace(microsecond=0).isoformat()


def _home(home=None) -> Path:
    if home:
        return Path(home)
    return Path(os.environ.get("NOX_HOME") or (r"C:\NOX" if os.name == "nt" else str(Path.home() / "NOX")))


def voice_dir(home=None) -> Path:
    return _home(home) / "voice"


def _read_license(folder: Path) -> str:
    for name in ("LICENSE", "LICENSE.txt", "LICENSE.md", "license.json"):
        p = folder / name
        if p.is_file():
            try:
                return p.read_text(encoding="utf-8", errors="replace")[:8000]
            except Exception:
                return ""
    meta = folder / "voices.json"
    if meta.is_file():
        try:
            data = json.loads(meta.read_text(encoding="utf-8"))
            return str(data.get("license") or data.get("licence") or "")
        except Exception:
            return ""
    return ""


def _license_ok(text: str) -> bool:
    t = (text or "").lower()
    if "openrail" in t or "responsible ai" in t:
        return False
    return any(tag in t for tag in PERMISSIVE)


def probe_kokoro(home=None) -> dict[str, Any]:
    root = voice_dir(home) / "kokoro"
    if not root.is_dir():
        return {
            "engine": "kokoro",
            "status": "HOLD",
            "reason": "официальный Kokoro-82M (Apache-2.0) не поддерживает русский; локальный пакет не установлен",
            "license": "Apache-2.0 (upstream, без RU)",
            "ru": False,
        }
    lic = _read_license(root)
    meta = {}
    if (root / "voices.json").is_file():
        try:
            meta = json.loads((root / "voices.json").read_text(encoding="utf-8"))
        except Exception:
            meta = {}
    langs = [str(x).lower() for x in (meta.get("languages") or meta.get("langs") or [])]
    ru = any(x.startswith("ru") for x in langs) or bool(meta.get("ru"))
    if not _license_ok(lic or str(meta.get("license") or "")):
        return {"engine": "kokoro", "status": "HOLD", "reason": "лицензия локального пакета не permissive (или OpenRAIL)", "license": (lic or str(meta.get("license") or "UNKNOWN"))[:80], "ru": ru}
    if not ru:
        return {"engine": "kokoro", "status": "HOLD", "reason": "локальный Kokoro установлен, но в манифесте нет русского", "license": (lic or "present")[:80], "ru": False}
    return {"engine": "kokoro", "status": "READY", "reason": "локальный permissive-пакет с ru", "license": (lic.splitlines()[0] if lic else "permissive")[:80], "ru": True}


def probe_sapi(runner=None) -> dict[str, Any]:
    """Probe installed local Windows SAPI RU and ES voices; do not claim audio on Linux."""
    if os.name != "nt" and runner is None:
        return {"engine": "windows-sapi", "status": "HOLD", "reason": "Windows SAPI unavailable on this operating system", "voices": [], "ru": False, "es": False}
    if runner is not None:
        try:
            voices = list(runner())
        except Exception as e:
            return {"engine": "windows-sapi", "status": "HOLD", "reason": type(e).__name__, "voices": [], "ru": False, "es": False}
    else:
        script = (
            "Add-Type -AssemblyName System.Speech; "
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "$s.GetInstalledVoices() | ForEach-Object { "
            "$_.VoiceInfo.Name + '|' + $_.VoiceInfo.Culture.Name + '|' + $_.Enabled }; "
            "$s.Dispose()"
        )
        try:
            exe = shutil.which("powershell") or shutil.which("pwsh")
            if not exe:
                return {"engine": "windows-sapi", "status": "HOLD", "reason": "PowerShell not installed", "voices": [], "ru": False, "es": False}
            raw = subprocess.check_output([exe, "-NoProfile", "-Command", script], timeout=9, stderr=subprocess.DEVNULL)
            voices = []
            for line in raw.decode("utf-8", "replace").splitlines():
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 2:
                    voices.append({"name": parts[0], "lang": parts[1], "enabled": (parts[2].lower() == "true") if len(parts) > 2 else True})
        except Exception as e:
            return {"engine": "windows-sapi", "status": "HOLD", "reason": "SAPI probe failed: " + type(e).__name__, "voices": [], "ru": False, "es": False}
    valid = [v for v in voices if isinstance(v, dict) and isinstance(v.get("name"), str) and v.get("enabled") is not False]
    available = {
        lang: [v for v in valid if str(v.get("lang") or "").lower().startswith(lang)]
        for lang in ("ru", "es")
    }
    return {"engine": "windows-sapi", "status": "READY" if any(available.values()) else "HOLD",
            "voices": valid, "ru": bool(available["ru"]), "es": bool(available["es"]),
            "by_language": available,
            "reason": "Local OS voice(s) detected" if any(available.values()) else "No suitable RU/ES Windows voice installed"}


def status(home=None, *, sapi_runner=None, lang="ru") -> dict[str, Any]:
    """Language-specific readiness: only an installed, runnable SAPI engine can be READY."""
    language = str(lang or "ru").lower().split("-")[0]
    if language not in ("ru", "es"):
        return {"status": "HOLD", "tts_available": False, "language": language,
                "reason": "Only Russian and Spanish supported", "at": _now()}
    kokoro = probe_kokoro(home)
    sapi = probe_sapi(runner=sapi_runner)
    selected = (sapi.get("by_language") or {}).get(language) or []
    ready = bool(selected)
    return {"status": "READY" if ready else "HOLD", "engine": "windows-sapi" if ready else None,
            "reason": "Local Windows SAPI voice detected" if ready else "A local " + language.upper() + " SAPI voice is not installed; Kokoro synthesis runtime is not integrated",
            "tts_available": ready, "language": language, "ru": sapi.get("ru", False), "es": sapi.get("es", False),
            "selected_voice": selected[0].get("name") if ready else None,
            "windows_sapi": sapi, "kokoro": kokoro,
            "kokoro_runtime_available": False,
            "at": _now(), "note": "This reports installed voices; native WAV generation must be checked separately. No cloud TTS."}


def synthesize(text: str, dest: Path | None = None, home=None, *, sapi_runner=None, lang="ru") -> dict[str, Any]:
    """Generate a genuine WAV using Windows SAPI for the requested RU/ES language."""
    st = status(home, sapi_runner=sapi_runner, lang=lang)
    if st.get("status") != "READY":
        return {"status": "HOLD", "reason": st.get("reason"), "path": None, "language": st.get("language")}
    if os.name != "nt":
        return {"status": "HOLD", "reason": "SAPI synthesis is Windows-only (test fixture cannot produce speech)", "path": None, "language": st.get("language")}
    content = (text or "").strip()
    if not content:
        return {"status": "HOLD", "reason": "empty text", "path": None, "language": st.get("language")}
    from uuid import uuid4
    output = Path(dest or (Path(tempfile.gettempdir()) / ("nox_tts_" + uuid4().hex + ".wav")))
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        return {"status": "HOLD", "reason": "output already exists; refusing overwrite", "path": None, "language": st.get("language")}
    voice = st["selected_voice"]
    vs = voice.replace("'", "''")
    tx = content[:800].replace("'", "''")
    path = str(output).replace("'", "''")
    command = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "try { $s.SelectVoice('%s'); $s.SetOutputToWaveFile('%s'); $s.Speak('%s'); } "
        "finally { $s.Dispose() }"
    ) % (vs, path, tx)
    try:
        exe = shutil.which("powershell") or shutil.which("pwsh")
        if not exe:
            return {"status": "HOLD", "reason": "PowerShell missing", "path": None, "language": st.get("language")}
        subprocess.check_call([exe, "-NoProfile", "-Command", command], timeout=40,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if output.is_file() and output.stat().st_size >= 44:
            with output.open("rb") as fp:
                header = fp.read(12)
            if header[:4] == b"RIFF" and header[8:] == b"WAVE":
                return {"status": "READY", "engine": "windows-sapi", "path": str(output),
                        "language": st["language"], "voice": voice, "bytes": output.stat().st_size}
    except Exception as e:
        return {"status": "HOLD", "reason": "SAPI synthesis failed: " + type(e).__name__, "path": None, "language": st.get("language")}
    return {"status": "HOLD", "reason": "No valid WAV generated", "path": None, "language": st.get("language")}
