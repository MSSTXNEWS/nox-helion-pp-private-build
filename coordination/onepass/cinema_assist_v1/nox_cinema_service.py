"""Local translation and optional voice endpoint for NOX Cinema Assist.

Run on loopback. ASR is provided by the separately started WhisperLiveKit server.
Model files must already exist locally; this service never downloads models.
"""
from __future__ import annotations

import argparse
import io
import os
import secrets
import tempfile
import threading
import time
import uuid
import wave
from pathlib import Path
from typing import Dict, Tuple

from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent
TRANSLATOR_PATH = Path(os.environ.get("NOX_OPUS_MT_MODEL", ROOT / "models" / "opus-mt-es-ru"))
XTTS_PATH = Path(os.environ.get("NOX_XTTS_MODEL", ROOT / "models" / "xtts-v2"))
XTTS_CONFIG = XTTS_PATH / "config.json"
TOKEN = os.environ.get("NOX_CINEMA_API_TOKEN", "")
ORIGINS = [x.strip() for x in os.environ.get("NOX_CINEMA_ALLOWED_ORIGINS", "http://127.0.0.1:18775,http://localhost:18775").split(",") if x.strip()]

app = FastAPI(title="NOX Cinema Language Assist", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=ORIGINS, allow_methods=["GET", "POST"], allow_headers=["Content-Type", "X-NOX-Cinema-Token"])

_translator = None
_translator_device = "unloaded"
_tts = None
_tts_lock = threading.Lock()
_profiles: Dict[str, Tuple[bytes, float]] = {}
_profiles_lock = threading.Lock()


class TranslateRequest(BaseModel):
    text: str = Field(min_length=1, max_length=900)
    source: str = "es"
    target: str = "ru"


class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=420)
    language: str = "ru"
    profile_id: str = ""


def _authorized(value: str | None) -> bool:
    return not TOKEN or (value is not None and secrets.compare_digest(value, TOKEN))


def _check_auth(value: str | None) -> None:
    if not _authorized(value):
        raise HTTPException(status_code=401, detail="NOX_CINEMA_AUTH_REQUIRED")


def _load_translator():
    global _translator, _translator_device
    if _translator is None:
        if not TRANSLATOR_PATH.is_dir():
            raise HTTPException(status_code=503, detail="LOCAL_TRANSLATION_MODEL_NOT_INSTALLED")
        try:
            import torch
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
            _translator_device = "cuda" if torch.cuda.is_available() else "cpu"
            tokenizer = AutoTokenizer.from_pretrained(str(TRANSLATOR_PATH), local_files_only=True)
            model = AutoModelForSeq2SeqLM.from_pretrained(str(TRANSLATOR_PATH), local_files_only=True)
            model.to(_translator_device)
            model.eval()
            _translator = (torch, tokenizer, model)
        except Exception as exc:
            raise HTTPException(status_code=503, detail="TRANSLATION_MODEL_LOAD_FAILED:" + type(exc).__name__) from exc
    return _translator


def _translate(text: str) -> str:
    torch, tokenizer, model = _load_translator()
    with torch.inference_mode():
        inputs = tokenizer([text], return_tensors="pt", truncation=True, max_length=512)
        inputs = {k: v.to(_translator_device) for k, v in inputs.items()}
        generated = model.generate(**inputs, max_new_tokens=160, num_beams=2)
        return tokenizer.batch_decode(generated, skip_special_tokens=True)[0].strip()


def _load_tts():
    global _tts
    if _tts is None:
        if not XTTS_CONFIG.is_file() or not (XTTS_PATH / "model.pth").is_file():
            raise HTTPException(status_code=503, detail="LOCAL_XTTS_MODEL_NOT_INSTALLED")
        try:
            from TTS.api import TTS
            use_gpu = os.environ.get("NOX_XTTS_DEVICE", "auto") != "cpu"
            _tts = TTS(model_path=str(XTTS_PATH / "model.pth"), config_path=str(XTTS_CONFIG), progress_bar=False, gpu=use_gpu)
        except Exception as exc:
            raise HTTPException(status_code=503, detail="XTTS_LOAD_FAILED:" + type(exc).__name__) from exc
    return _tts


def _profile_bytes(profile_id: str) -> bytes | None:
    if not profile_id:
        return None
    with _profiles_lock:
        now = time.monotonic()
        for key, (_, expiry) in list(_profiles.items()):
            if expiry <= now:
                _profiles.pop(key, None)
        item = _profiles.get(profile_id)
        return item[0] if item else None


def _synthesize(text: str, profile_id: str) -> bytes:
    import numpy as np
    voice = _profile_bytes(profile_id)
    if voice is None:
        raise HTTPException(status_code=409, detail="VOICE_PROFILE_REQUIRED_OR_EXPIRED")
    engine = _load_tts()
    tmp_path = None
    try:
        kwargs = {"text": text, "language": "ru"}
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(voice)
            tmp_path = tmp.name
        kwargs["speaker_wav"] = tmp_path
        with _tts_lock:
            samples = np.asarray(engine.tts(**kwargs), dtype=np.float32)
        samples = np.clip(samples, -1.0, 1.0)
        pcm = (samples * 32767).astype("<i2").tobytes()
        output = io.BytesIO()
        with wave.open(output, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(int(engine.synthesizer.output_sample_rate))
            wav.writeframes(pcm)
        return output.getvalue()
    finally:
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)


@app.get("/api/cinema/health")
def health(x_nox_cinema_token: str | None = Header(default=None)):
    _check_auth(x_nox_cinema_token)
    translation_files = (TRANSLATOR_PATH / "config.json", TRANSLATOR_PATH / "pytorch_model.bin", TRANSLATOR_PATH / "source.spm", TRANSLATOR_PATH / "target.spm")
    tts_files = (XTTS_CONFIG, XTTS_PATH / "model.pth", XTTS_PATH / "dvae.pth", XTTS_PATH / "vocab.json", XTTS_PATH / "speakers_xtts.pth")
    return {
        "service": "nox-cinema-language-assist",
        "translation_ready": all(path.is_file() for path in translation_files),
        "translation_loaded": _translator is not None,
        "translation_device": _translator_device,
        "tts_ready": all(path.is_file() for path in tts_files),
        "tts_loaded": _tts is not None,
        "asr_url": os.environ.get("NOX_CINEMA_ASR_WS", "ws://127.0.0.1:8000/v1/listen"),
        "audio_persistence": "none",
        "voice_profile_persistence": "memory-only; expires after 20 minutes",
    }


@app.post("/api/cinema/translate")
def translate(req: TranslateRequest, x_nox_cinema_token: str | None = Header(default=None)):
    _check_auth(x_nox_cinema_token)
    if req.source != "es" or req.target != "ru":
        raise HTTPException(status_code=400, detail="ONLY_ES_TO_RU_IS_CONFIGURED")
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="EMPTY_TEXT")
    # FastAPI's sync route is already executed in its worker pool.
    return {"translation": _translate(req.text.strip()), "source": "es", "target": "ru", "engine": "Helsinki-NLP/opus-mt-es-ru"}


@app.post("/api/cinema/voice-profiles")
async def voice_profile(file: UploadFile = File(...), x_nox_cinema_token: str | None = Header(default=None)):
    _check_auth(x_nox_cinema_token)
    if not file.filename or not file.filename.lower().endswith(".wav"):
        raise HTTPException(status_code=415, detail="WAV_FILE_REQUIRED")
    content = await file.read(20 * 1024 * 1024 + 1)
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="VOICE_SAMPLE_TOO_LARGE")
    try:
        with wave.open(io.BytesIO(content), "rb") as wav:
            duration = wav.getnframes() / max(1, wav.getframerate())
            if duration < 2 or duration > 20 or wav.getnchannels() not in (1, 2):
                raise HTTPException(status_code=400, detail="WAV_SAMPLE_MUST_BE_2_TO_20_SECONDS")
    except wave.Error as exc:
        raise HTTPException(status_code=400, detail="INVALID_WAV_SAMPLE") from exc
    key = uuid.uuid4().hex
    with _profiles_lock:
        while len(_profiles) >= 5:
            _profiles.pop(next(iter(_profiles)))
        _profiles[key] = (content, time.monotonic() + 1200)
    return {"profile_id": key, "stored": "memory-only", "expires_in_seconds": 1200}


@app.post("/api/cinema/tts")
def tts(req: TTSRequest, x_nox_cinema_token: str | None = Header(default=None)):
    _check_auth(x_nox_cinema_token)
    if req.language != "ru":
        raise HTTPException(status_code=400, detail="ONLY_RUSSIAN_TTS_IS_CONFIGURED")
    if not _profile_bytes(req.profile_id):
        raise HTTPException(status_code=409, detail="VOICE_PROFILE_REQUIRED_OR_EXPIRED")
    audio = _synthesize(req.text.strip(), req.profile_id)
    return Response(content=audio, media_type="audio/wav", headers={"Cache-Control": "no-store"})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.environ.get("NOX_CINEMA_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("NOX_CINEMA_PORT", "18776")))
    args = parser.parse_args()
    if args.host not in ("127.0.0.1", "localhost", "::1") and not TOKEN:
        parser.error("Binding outside loopback requires NOX_CINEMA_API_TOKEN")
    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
