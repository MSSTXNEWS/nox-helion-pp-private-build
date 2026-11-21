"""Общие утилиты voice: env, аудио (WAV/PCM16/ffmpeg), ресемплинг, HTTP-хелперы."""
import array
import http.server
import importlib.util
import io
import json
import os
import shutil
import struct
import subprocess
import sys
import wave

SR = 16000


def env(name, default=None):
    v = os.environ.get(name)
    return default if v is None or v == "" else v


def env_int(name, default):
    try:
        return int(env(name, default))
    except (TypeError, ValueError):
        return default


def env_float(name, default):
    try:
        return float(env(name, default))
    except (TypeError, ValueError):
        return default


def env_bool(name, default=False):
    v = env(name)
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "on", "y")


def have_module(name):
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


class AudioError(Exception):
    """Аудио нельзя разобрать (формат/декодер)."""


def to_samples(pcm):
    b = bytes(pcm)
    b = b[: len(b) - (len(b) % 2)]
    a = array.array("h")
    a.frombytes(b)
    if sys.byteorder == "big":
        a.byteswap()
    return a


def from_samples(samples):
    a = samples if isinstance(samples, array.array) else array.array("h", samples)
    if sys.byteorder == "big":
        a = array.array("h", a)
        a.byteswap()
    return a.tobytes()


def resample_pcm16(pcm, src, dst):
    """Линейная интерполяция mono int16. Для речи достаточно; без numpy."""
    if src == dst or not pcm:
        return bytes(pcm)
    s = to_samples(pcm)
    n = len(s)
    if n < 2:
        return from_samples(s)
    m = max(1, int(round(n * dst / float(src))))
    ratio = (n - 1) / float(max(1, m - 1)) if m > 1 else 0.0
    out = array.array("h", [0]) * m
    for i in range(m):
        pos = i * ratio
        j = int(pos)
        fr = pos - j
        a = s[j]
        b = s[j + 1] if j + 1 < n else a
        out[i] = int(a + (b - a) * fr)
    return from_samples(out)


def make_wav(pcm, rate=SR, channels=1):
    bio = io.BytesIO()
    with wave.open(bio, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(pcm))
    return bio.getvalue()


def wav_stream_header(rate, channels=1):
    """Заголовок WAV с «неизвестной» длиной (0xFFFFFFFF) - для chunked-потока."""
    return (b"RIFF" + struct.pack("<I", 0xFFFFFFFF) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, channels, rate, rate * 2 * channels, 2 * channels, 16)
            + b"data" + struct.pack("<I", 0xFFFFFFFF))


def decode_wav(data):
    """WAV (PCM 16 бит) -> (pcm16 mono bytes, rate)."""
    try:
        with wave.open(io.BytesIO(data), "rb") as w:
            ch, sw, rate, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
            raw = w.readframes(n)
    except (wave.Error, EOFError) as e:
        raise AudioError("bad WAV: %s" % e)
    if sw != 2:
        raise AudioError("WAV sample width %d bytes unsupported (need PCM16); convert with ffmpeg" % sw)
    s = to_samples(raw)
    if ch > 1:
        s = array.array("h", [int(sum(s[i:i + ch]) / ch) for i in range(0, len(s) - ch + 1, ch)])
    return from_samples(s), rate


def ffmpeg_path():
    return shutil.which(env("NOX_FFMPEG", "ffmpeg") or "ffmpeg")


def decode_with_ffmpeg(data, rate=SR, timeout=60):
    ff = ffmpeg_path()
    if not ff:
        raise AudioError("ffmpeg not found: webm/opus/mp3/ogg not supported; send WAV or raw PCM16 16kHz mono")
    try:
        p = subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-i", "pipe:0", "-f", "s16le", "-ac", "1", "-ar", str(rate), "pipe:1"],
                           input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise AudioError("ffmpeg timeout")
    if p.returncode != 0 or not p.stdout:
        raise AudioError("ffmpeg failed: %s" % p.stderr.decode("utf-8", "ignore")[:200])
    return p.stdout


def decode_audio(data, content_type="", fmt="auto", rate=SR):
    """Любое поддерживаемое аудио -> PCM16 mono `rate` Гц.
    fmt: auto | pcm16 (сырой LE 16 кГц mono) | wav | any (через ffmpeg)."""
    ct = (content_type or "").split(";")[0].strip().lower()
    if not data:
        raise AudioError("empty audio body")
    if fmt == "auto":
        if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
            fmt = "wav"
        elif ct in ("audio/l16", "audio/pcm", "audio/x-pcm", "audio/raw") or ct.startswith("audio/l16"):
            fmt = "pcm16"
        elif ct in ("audio/webm", "audio/ogg", "audio/opus", "audio/mpeg", "audio/mp4", "video/webm") or data[:4] in (b"\x1aE\xdf\xa3", b"OggS", b"ID3\x03") :
            fmt = "any"
        else:
            fmt = "pcm16"
    if fmt == "pcm16":
        return data[: len(data) - (len(data) % 2)]
    if fmt == "wav":
        pcm, r = decode_wav(data)
        return resample_pcm16(pcm, r, rate)
    if fmt == "any":
        return decode_with_ffmpeg(data, rate)
    raise AudioError("unknown format %r" % fmt)


# ---------------- HTTP ----------------
class JsonHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "NoxVoice/1"
    max_body = 64 * 1024 * 1024

    def log_message(self, fmt, *args):
        if env_bool("NOX_VOICE_LOG"):
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def read_body(self):
        te = (self.headers.get("Transfer-Encoding") or "").lower()
        if "chunked" in te:
            out = bytearray()
            while True:
                line = self.rfile.readline().strip()
                n = int(line.split(b";")[0] or b"0", 16)
                if n == 0:
                    self.rfile.readline()
                    break
                out += self.rfile.read(n)
                self.rfile.readline()
                if len(out) > self.max_body:
                    raise ValueError("body too large")
            return bytes(out)
        n = int(self.headers.get("Content-Length") or 0)
        if n > self.max_body:
            raise ValueError("body too large")
        return self.rfile.read(n) if n else b""

    def send_bytes(self, code, body, ctype="application/json", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, code, obj):
        self.send_bytes(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def json_body(self):
        raw = self.read_body()
        if not raw.strip():
            return {}
        try:
            o = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise ValueError("invalid JSON body")
        if not isinstance(o, dict):
            raise ValueError("JSON object expected")
        return o

    def start_chunked(self, ctype, extra=None):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Transfer-Encoding", "chunked")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()

    def write_chunk(self, data):
        if data:
            self.wfile.write(b"%x\r\n" % len(data) + data + b"\r\n")
            self.wfile.flush()

    def end_chunked(self):
        self.wfile.write(b"0\r\n\r\n")
        self.wfile.flush()

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", "0")
        self.end_headers()


class Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def serve(handler, host, port):
    srv = Server((host, port), handler)
    return srv
