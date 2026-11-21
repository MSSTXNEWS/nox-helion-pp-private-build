"""NOX voice loop: аудио-вход -> STT (HTTP) -> чат (HTTP, потоковый текст) -> TTS кусочками (HTTP) -> воспроизведение.
Барж-ин: речь пользователя во время озвучки останавливает озвучку и текущий ответ чата.

Запуск:
  python3 voice_loop.py --input mic --output play
  python3 voice_loop.py --input file:question.wav --output file:/tmp/out --once      # без микрофона (тест)
URL по умолчанию из env: NOX_STT_URL, NOX_TTS_URL, NOX_VOICE_CHAT_URL (+ NOX_VOICE_CHAT_FORMAT=nox|openai|plain).
"""
import argparse
import base64
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from voice import common  # noqa: E402
from voice.common import env, env_bool, env_float, env_int, SR  # noqa: E402

CHUNK_MS = 200


# ---------------- HTTP-клиенты ----------------
def _http(url, data=None, ctype="application/json", timeout=30, method=None):
    req = urllib.request.Request(url, data=data, headers={"Content-Type": ctype}, method=method)
    return urllib.request.urlopen(req, timeout=timeout)


def _post_json(url, obj, timeout=30):
    with _http(url, json.dumps(obj, ensure_ascii=False).encode("utf-8"), timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8") or "{}")


class SttClient:
    def __init__(self, url, language=None):
        self.url = url.rstrip("/")
        self.language = language
        self.sid = None

    def start(self):
        o = {"language": self.language} if self.language else {}
        self.sid = _post_json(self.url + "/stream/start", o)["id"]
        return self.sid

    def chunk(self, pcm):
        with _http("%s/stream/%s/chunk" % (self.url, self.sid), bytes(pcm), "audio/L16; rate=16000", timeout=120) as r:
            return json.loads(r.read().decode("utf-8"))

    def finish(self):
        return _post_json("%s/stream/%s/finish" % (self.url, self.sid), {}, timeout=120)

    def close(self):
        try:
            _post_json("%s/stream/%s/close" % (self.url, self.sid), {}, timeout=5)
        except Exception:
            pass


class TtsClient:
    def __init__(self, url, lang="auto"):
        self.url = url.rstrip("/")
        self.lang = lang

    def start(self):
        return _post_json(self.url + "/session", {"lang": self.lang})["id"]

    def push(self, sid, text, final=False):
        return _post_json("%s/session/%s/text" % (self.url, sid), {"text": text, "final": final})

    def stop(self, sid):
        try:
            _post_json("%s/session/%s/stop" % (self.url, sid), {}, timeout=5)
        except Exception:
            pass

    def events(self, sid):
        """Генератор событий (audio -> dict c bytes в 'pcm')."""
        with _http("%s/session/%s/audio?format=sse" % (self.url, sid), None, timeout=300, method="GET") as r:
            for raw in r:
                ln = raw.decode("utf-8", "ignore").strip()
                if not ln.startswith("data:"):
                    continue
                try:
                    e = json.loads(ln[5:])
                except ValueError:
                    continue
                if "pcm_b64" in e:
                    e["pcm"] = base64.b64decode(e.pop("pcm_b64"))
                yield e
                if e.get("type") in ("end", "cancelled", "timeout"):
                    return


class ChatClient:
    """Потоковый чат. Форматы: nox (data: {"type":"token","text"}), openai (choices[0].delta.content), plain (сырые куски текста)."""

    def __init__(self, url, fmt="nox", token=None, model=None):
        self.url, self.fmt, self.token, self.model = url, fmt, token, model

    def stream(self, messages, cancel=None):
        body = {"messages": messages, "stream": True}
        if self.model:
            body["model"] = self.model
        req = urllib.request.Request(self.url, json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                     {"Content-Type": "application/json"})
        if self.token:
            req.add_header("Authorization", "Bearer " + self.token)
        r = urllib.request.urlopen(req, timeout=env_float("NOX_VOICE_CHAT_TIMEOUT", 300))
        try:
            if self.fmt == "plain":
                while True:
                    b = r.read1(256) if hasattr(r, "read1") else r.read(256)
                    if not b or (cancel and cancel.is_set()):
                        return
                    yield b.decode("utf-8", "ignore")
            for raw in r:
                if cancel and cancel.is_set():
                    return
                ln = raw.decode("utf-8", "ignore").strip()
                if not ln.startswith("data:"):
                    continue
                payload = ln[5:].strip()
                if payload == "[DONE]":
                    return
                try:
                    o = json.loads(payload)
                except ValueError:
                    continue
                if self.fmt == "openai":
                    ch = (o.get("choices") or [{}])[0]
                    d = (ch.get("delta") or {}).get("content")
                    if d:
                        yield d
                else:
                    if o.get("type") == "token" and o.get("text"):
                        yield o["text"]
                    elif o.get("type") in ("done", "error"):
                        if o.get("type") == "error":
                            raise RuntimeError(str(o.get("message") or o)[:200])
                        return
        finally:
            r.close()


# ---------------- источники аудио ----------------
class FileSource:
    """WAV/PCM файл -> куски по chunk_ms; в конце добавляет tail_silence секунд тишины (чтобы сработал end_of_turn)."""

    def __init__(self, path, realtime=False, tail_silence=2.0, lead_silence=0.0):
        with open(path, "rb") as f:
            data = f.read()
        self.pcm = common.decode_audio(data, "", "auto" if path.lower().endswith((".wav", ".webm", ".ogg", ".mp3", ".opus", ".m4a")) else "pcm16")
        self.pcm = b"\x00\x00" * int(lead_silence * SR) + self.pcm + b"\x00\x00" * int(tail_silence * SR)
        self.realtime = realtime

    def __iter__(self):
        n = SR * CHUNK_MS // 1000 * 2
        for i in range(0, len(self.pcm), n):
            yield self.pcm[i:i + n]
            if self.realtime:
                time.sleep(CHUNK_MS / 1000.0)


class ListSource:
    """Готовые куски PCM (для тестов)."""

    def __init__(self, chunks, realtime=False):
        self.chunks, self.realtime = chunks, realtime

    def __iter__(self):
        for c in self.chunks:
            yield c
            if self.realtime:
                time.sleep(CHUNK_MS / 1000.0)


class StdinSource:
    def __iter__(self):
        n = SR * CHUNK_MS // 1000 * 2
        while True:
            b = sys.stdin.buffer.read(n)
            if not b:
                return
            yield b


class MicSource:
    """Микрофон через внешний процесс (по умолчанию arecord). NOX_VOICE_MIC_CMD переопределяет команду
    (должна писать сырой PCM16 LE 16 кГц mono в stdout). Нет arecord/ffmpeg -> честная ошибка."""

    def __init__(self):
        cmd = env("NOX_VOICE_MIC_CMD")
        if cmd:
            import shlex
            self.cmd = shlex.split(cmd)
        elif shutil.which("arecord"):
            self.cmd = ["arecord", "-q", "-t", "raw", "-f", "S16_LE", "-r", str(SR), "-c", "1"]
        elif common.ffmpeg_path():
            self.cmd = [common.ffmpeg_path(), "-loglevel", "error", "-f", env("NOX_VOICE_MIC_FFMPEG_FMT", "pulse"), "-i", "default",
                        "-f", "s16le", "-ac", "1", "-ar", str(SR), "pipe:1"]
        else:
            raise RuntimeError("no microphone capture tool: install alsa-utils (arecord) or set NOX_VOICE_MIC_CMD; "
                               "on a headless server use --input file:... or --input stdin")
        self.proc = None

    def __iter__(self):
        self.proc = subprocess.Popen(self.cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        n = SR * CHUNK_MS // 1000 * 2
        try:
            while True:
                b = self.proc.stdout.read(n)
                if not b:
                    return
                yield b
        finally:
            self.proc.kill()


# ---------------- выход аудио ----------------
class Sink:
    """Базовый приёмник. busy() - ещё «звучит» (по накопленной длительности); stop() обрывает."""

    def __init__(self):
        self._until = 0.0
        self.stopped_count = 0
        self.lock = threading.Lock()

    def play(self, pcm, rate):
        with self.lock:
            now = time.time()
            self._until = max(now, self._until) + len(pcm) / 2.0 / rate
        self._write(pcm, rate)

    def _write(self, pcm, rate):
        pass

    def busy(self):
        return time.time() < self._until

    def stop(self):
        with self.lock:
            self._until = 0.0
            self.stopped_count += 1
        self._stop()

    def _stop(self):
        pass

    def close(self):
        pass


class MemorySink(Sink):
    def __init__(self, realtime_busy=True):
        Sink.__init__(self)
        self.chunks = []
        self.realtime_busy = realtime_busy

    def _write(self, pcm, rate):
        self.chunks.append((bytes(pcm), rate))


class FileSink(Sink):
    """Пишет ответ каждой реплики в WAV: <dir>/reply_<n>.wav (кусочки одной реплики склеиваются)."""

    def __init__(self, directory):
        Sink.__init__(self)
        os.makedirs(directory, exist_ok=True)
        self.dir = directory
        self.n = 0
        self.cur = bytearray()
        self.rate = 24000
        self.files = []

    def _write(self, pcm, rate):
        self.cur += pcm
        self.rate = rate

    def end_turn(self):
        if self.cur:
            self.n += 1
            p = os.path.join(self.dir, "reply_%d.wav" % self.n)
            with open(p, "wb") as f:
                f.write(common.make_wav(bytes(self.cur), self.rate))
            self.files.append(p)
            self.cur = bytearray()

    def _stop(self):
        self.end_turn()

    def busy(self):
        return False


class PlaySink(Sink):
    """Воспроизведение через aplay/paplay/ffplay (NOX_VOICE_PLAY_CMD с {rate} переопределяет)."""

    def __init__(self):
        Sink.__init__(self)
        self.proc = None
        self.rate = None

    def _cmd(self, rate):
        c = env("NOX_VOICE_PLAY_CMD")
        if c:
            import shlex
            return [x.replace("{rate}", str(rate)) for x in shlex.split(c)]
        if shutil.which("aplay"):
            return ["aplay", "-q", "-t", "raw", "-f", "S16_LE", "-r", str(rate), "-c", "1"]
        if shutil.which("paplay"):
            return ["paplay", "--raw", "--format=s16le", "--rate=%d" % rate, "--channels=1"]
        if shutil.which("ffplay"):
            return ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", "-f", "s16le", "-ar", str(rate), "-ac", "1", "-i", "pipe:0"]
        raise RuntimeError("no audio player (aplay/paplay/ffplay); use --output file:DIR")

    def _write(self, pcm, rate):
        if self.proc is None or self.proc.poll() is not None:
            self.proc = subprocess.Popen(self._cmd(rate), stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
            self.rate = rate
        try:
            self.proc.stdin.write(pcm)
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError):
            self.proc = None

    def _stop(self):
        p, self.proc = self.proc, None
        if p:
            try:
                p.kill()
            except OSError:
                pass

    def close(self):
        p, self.proc = self.proc, None
        if p:
            try:
                p.stdin.close()
                p.wait(timeout=30)
            except Exception:
                p.kill()


# ---------------- цикл ----------------
class VoiceLoop:
    SENT_END = tuple(".!?…\n,;:")

    def __init__(self, source, sink, stt, tts, chat, system_prompt=None, barge_in=True, barge_min_ms=300,
                 log=None, flush_chars=40, flush_secs=0.3, max_history=12):
        self.source, self.sink, self.stt, self.tts, self.chat = source, sink, stt, tts, chat
        self.barge_in_enabled = barge_in
        self.barge_min_ms = barge_min_ms
        self.log = log or (lambda e: None)
        self.flush_chars, self.flush_secs, self.max_history = flush_chars, flush_secs, max_history
        self.system = system_prompt
        self.history = []
        self.pending_text = ""
        self.turn = None            # {"cancel": Event, "thread": Thread, "id": n, "tts": sid}
        self.turn_seq = 0
        self.lock = threading.Lock()
        self.result = {"turns": [], "barge_ins": 0, "errors": []}

    # --- состояние ---
    def speaking(self):
        t = self.turn
        return bool(t and t["thread"].is_alive()) or self.sink.busy()

    # --- события STT ---
    def on_event(self, ev):
        typ = ev.get("type")
        self.log(ev)
        if typ == "speech_start":
            if self.barge_in_enabled and self.speaking() and ev.get("speech_ms", 0) >= self.barge_min_ms:
                self.barge_in("speech_start")
        elif typ == "final":
            self.pending_text = (ev.get("text") or "").strip()
            self._lang = ev.get("language")
        elif typ == "end_of_turn":
            text, self.pending_text = self.pending_text, ""
            if text:
                self.start_turn(text)
        elif typ in ("error", "warning"):
            self.result["errors"].append(ev.get("message"))

    def barge_in(self, reason):
        t = self.turn
        self.result["barge_ins"] += 1
        self.log({"type": "barge_in", "reason": reason})
        if t:
            t["cancel"].set()
            t["barged"] = True
            if t.get("tts"):
                self.tts.stop(t["tts"])
        self.sink.stop()

    # --- реплика ---
    def start_turn(self, text):
        with self.lock:
            old = self.turn
            if old and old["thread"].is_alive():
                old["cancel"].set()
                if old.get("tts"):
                    self.tts.stop(old["tts"])
                self.sink.stop()
            self.turn_seq += 1
            t = {"id": self.turn_seq, "cancel": threading.Event(), "user": text, "reply": "", "spoken": 0, "barged": False, "tts": None}
            t["thread"] = threading.Thread(target=self._run_turn, args=(t,), daemon=True)
            self.turn = t
            self.history.append({"role": "user", "content": text})
            del self.history[:-self.max_history]
            msgs = ([{"role": "system", "content": self.system}] if self.system else []) + list(self.history)
            t["messages"] = msgs
            t["thread"].start()

    def _player(self, t, sid):
        try:
            for e in self.tts.events(sid):
                if t["cancel"].is_set():
                    break
                if e.get("type") == "audio":
                    t["spoken"] += 1
                    self.log({"type": "tts_audio", "seq": e.get("seq"), "text": e.get("text"), "backend": e.get("backend")})
                    self.sink.play(e["pcm"], e.get("sample_rate", 24000))
                elif e.get("type") == "error":
                    self.result["errors"].append("tts: %s" % e.get("message"))
        except Exception as ex:
            self.result["errors"].append("tts stream: %s" % ex)

    def _run_turn(self, t):
        sid = None
        player = None
        try:
            sid = self.tts.start()
            t["tts"] = sid
            player = threading.Thread(target=self._player, args=(t, sid), daemon=True)
            player.start()
            buf, last = "", time.time()
            for d in self.chat.stream(t["messages"], t["cancel"]):
                if t["cancel"].is_set():
                    break
                t["reply"] += d
                buf += d
                if len(buf) >= self.flush_chars or buf.endswith(self.SENT_END) or time.time() - last >= self.flush_secs:
                    self.tts.push(sid, buf)
                    buf, last = "", time.time()
            if not t["cancel"].is_set():
                self.tts.push(sid, buf, final=True)
        except Exception as ex:
            self.result["errors"].append("chat: %s: %s" % (type(ex).__name__, ex))
            if sid and not t["cancel"].is_set():
                try:
                    self.tts.push(sid, "", final=True)
                except Exception:
                    pass
        finally:
            if player:
                player.join(timeout=env_float("NOX_VOICE_PLAYER_JOIN", 300))
            if hasattr(self.sink, "end_turn") and not t["barged"]:
                self.sink.end_turn()
            with self.lock:
                if t["reply"].strip():
                    self.history.append({"role": "assistant", "content": t["reply"].strip()})
                    del self.history[:-self.max_history]
            self.result["turns"].append({"id": t["id"], "user": t["user"], "reply": t["reply"], "phrases_spoken": t["spoken"],
                                         "barged_in": t["barged"]})
            self.log({"type": "turn_done", "id": t["id"], "barged_in": t["barged"]})

    # --- главный цикл ---
    def run(self, once=False, drain_timeout=None):
        self.stt.start()
        try:
            for chunk in self.source:
                if not chunk:
                    continue
                if not self.barge_in_enabled and self.speaking():
                    continue                      # полудуплекс: пока говорим, микрофон не слушаем
                r = self.stt.chunk(chunk)
                for ev in r.get("events", []):
                    self.on_event(ev)
                if once and self.result["turns"]:
                    break
            for ev in self.stt.finish().get("events", []):
                self.on_event(ev)
            self.wait_idle(drain_timeout)
        finally:
            self.stt.close()
            self.sink.close()
        return self.result

    def wait_idle(self, timeout=None):
        end = time.time() + (timeout if timeout is not None else env_float("NOX_VOICE_DRAIN_TIMEOUT", 600))
        while time.time() < end:
            t = self.turn
            if (not t or not t["thread"].is_alive()) and not self.sink.busy():
                return True
            time.sleep(0.05)
        return False


def build_source(spec, realtime=False, tail=2.0):
    if spec == "mic":
        return MicSource()
    if spec == "stdin":
        return StdinSource()
    if spec.startswith("file:"):
        return FileSource(spec[5:], realtime=realtime, tail_silence=tail)
    raise SystemExit("unknown --input %r (mic | stdin | file:PATH)" % spec)


def build_sink(spec):
    if spec == "play":
        return PlaySink()
    if spec.startswith("file:"):
        return FileSink(spec[5:])
    if spec == "null":
        return Sink()
    raise SystemExit("unknown --output %r (play | file:DIR | null)" % spec)


def main(argv=None):
    ap = argparse.ArgumentParser(description="NOX voice loop")
    ap.add_argument("--input", default=env("NOX_VOICE_INPUT", "mic"))
    ap.add_argument("--output", default=env("NOX_VOICE_OUTPUT", "play"))
    ap.add_argument("--stt-url", default=env("NOX_STT_URL", "http://127.0.0.1:8093"))
    ap.add_argument("--tts-url", default=env("NOX_TTS_URL", "http://127.0.0.1:8094"))
    ap.add_argument("--chat-url", default=env("NOX_VOICE_CHAT_URL", "http://127.0.0.1:8091/v1/chat/stream"))
    ap.add_argument("--chat-format", default=env("NOX_VOICE_CHAT_FORMAT", "nox"), choices=["nox", "openai", "plain"])
    ap.add_argument("--lang", default=env("NOX_VOICE_LANG", "auto"), help="ru | es | auto")
    ap.add_argument("--no-barge-in", action="store_true", help="полудуплекс: во время озвучки микрофон не слушается")
    ap.add_argument("--barge-min-ms", type=int, default=env_int("NOX_BARGE_MIN_MS", 300))
    ap.add_argument("--realtime", action="store_true", help="для file: подавать аудио в реальном темпе")
    ap.add_argument("--tail-silence", type=float, default=2.0)
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args(argv)
    system = env("NOX_VOICE_SYSTEM", "Ты голосовой ассистент. Отвечай коротко, живой речью, без markdown, списков и эмодзи. "
                 "Отвечай на языке собеседника (русский или испанский).")
    loop = VoiceLoop(build_source(a.input, a.realtime, a.tail_silence), build_sink(a.output),
                     SttClient(a.stt_url, None if a.lang == "auto" else a.lang), TtsClient(a.tts_url, a.lang),
                     ChatClient(a.chat_url, a.chat_format, env("NOX_VOICE_CHAT_TOKEN"), env("NOX_VOICE_CHAT_MODEL")),
                     system_prompt=system, barge_in=not a.no_barge_in, barge_min_ms=a.barge_min_ms,
                     log=lambda e: print(json.dumps({k: v for k, v in e.items() if k not in ("segments", "pcm")}, ensure_ascii=False), flush=True))
    try:
        res = loop.run(once=a.once)
    except urllib.error.URLError as e:
        print("ERROR: service unreachable: %s (check STT/TTS URLs and /health)" % e, file=sys.stderr)
        return 2
    except RuntimeError as e:
        print("ERROR: %s" % e, file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 0
    print(json.dumps({"summary": res}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
