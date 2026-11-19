#!/usr/bin/env python3
"""SHA-locked RU/ES SAPI upgrade to the existing NOX voice module.

Replaces only the module functions starting with probe_sapi; preserves upstream
license/provenance logic. No remote synthesis, no fictitious Kokoro runtime.
"""
import argparse,hashlib,pathlib,sys,json
ORIGINAL_SHA='dd34f8427001fdc0163b66f2d825f6ea487bb38435dc89d8acdc799ed4a82fea'
ANCHOR='def probe_sapi(runner=None) -> dict[str, Any]:\n'
BLOCK='''def probe_sapi(runner=None) -> dict[str, Any]:
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
'''

def patch(source:bytes)->bytes:
 if hashlib.sha256(source).hexdigest()!=ORIGINAL_SHA:raise ValueError('NOX_VOICE_ORIGINAL_SHA_DRIFT')
 text=source.decode('utf8')
 if text.count(ANCHOR)!=1:raise ValueError('NOX_VOICE_PROBE_ANCHOR_MISSING')
 return (text.split(ANCHOR,1)[0]+BLOCK).encode('utf8')

if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--source',type=pathlib.Path,required=True);a.add_argument('--output',type=pathlib.Path,required=True);v=a.parse_args()
 try:
  if v.output.exists():raise ValueError('OUTPUT_EXISTS_NO_OVERWRITE')
  data=patch(v.source.read_bytes());v.output.parent.mkdir(parents=True,exist_ok=True)
  with v.output.open('xb') as f:f.write(data)
  print(json.dumps({'input_sha256':ORIGINAL_SHA,'output_sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'source_only':True}))
 except Exception as e:
  print('NOX_VOICE_PATCH_HOLD',e,file=sys.stderr);sys.exit(2)
