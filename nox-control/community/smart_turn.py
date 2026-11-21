"""Определение «человек договорил» по сырому PCM 16 кГц mono int16 (little-endian).

Бэкенды:
  * "heuristic" - VAD на энергии + ZCR, адаптивный порог шума, адаптивная длина паузы (всегда доступен, stdlib);
  * "onnx"      - pipecat Smart Turn v3.x (если есть numpy, onnxruntime и файл модели; путь в
                  NOX_SMART_TURN_MODEL или аргумент model_path).
backend() честно возвращает активный бэкенд. Если ONNX недоступен или упал - работает эвристика.
"""
import array
import math
import os
import sys

SAMPLE_RATE = 16000
FRAME_MS = 20
FRAME = SAMPLE_RATE * FRAME_MS // 1000  # 320 отсчётов


def pcm_to_samples(pcm):
    """bytes (int16 LE) -> array('h'). Нечётный хвостовой байт отбрасывается."""
    if isinstance(pcm, (bytes, bytearray, memoryview)):
        b = bytes(pcm)
        b = b[: len(b) - (len(b) % 2)]
        a = array.array("h")
        a.frombytes(b)
        if sys.byteorder == "big":
            a.byteswap()
        return a
    return array.array("h", [max(-32768, min(32767, int(x))) for x in pcm])


def frame_features(samples):
    """Список (rms, zcr) на каждый полный кадр 20 мс. rms в единицах int16, zcr в [0,1]."""
    out = []
    for i in range(0, len(samples) - FRAME + 1, FRAME):
        fr = samples[i:i + FRAME]
        s = 0
        z = 0
        prev = fr[0]
        for x in fr:
            s += x * x
            if (x >= 0) != (prev >= 0):
                z += 1
            prev = x
        out.append((math.sqrt(s / FRAME), z / (FRAME - 1)))
    return out


class HeuristicVAD:
    """Адаптивный VAD. Шумовой пол = 10-й перцентиль энергий кадров (с нижней границей)."""

    MIN_RMS = 150.0       # абсолютный минимум для «речи» (~ -47 дБFS)
    SNR_FACTOR = 3.0      # порог = пол * фактор
    ZCR_NOISE = 0.45      # высокий ZCR при низкой энергии = шипение, не речь
    HANGOVER = 3          # кадров «удержания» речи

    def threshold(self, feats):
        if not feats:
            return self.MIN_RMS
        e = sorted(f[0] for f in feats)
        floor = e[int(0.10 * (len(e) - 1))]
        return max(self.MIN_RMS, floor * self.SNR_FACTOR)

    def flags(self, feats):
        thr = self.threshold(feats)
        raw = []
        for rms, zcr in feats:
            speech = rms > thr and not (zcr > self.ZCR_NOISE and rms < thr * 2.5)
            raw.append(speech)
        out = list(raw)
        hang = 0
        for i, v in enumerate(raw):
            if v:
                hang = self.HANGOVER
            elif hang > 0:
                out[i] = True
                hang -= 1
        # убрать одиночные щелчки (1 кадр между тишиной)
        for i in range(1, len(out) - 1):
            if out[i] and not out[i - 1] and not out[i + 1] and raw[i]:
                out[i] = False
        return out, thr


def _segments(flags):
    """[(start, end_exclusive)] кадров речи."""
    segs, start = [], None
    for i, f in enumerate(flags):
        if f and start is None:
            start = i
        elif not f and start is not None:
            segs.append((start, i))
            start = None
    if start is not None:
        segs.append((start, len(flags)))
    return segs


def heuristic_analyze(pcm, base_pause=0.6, min_speech=0.15):
    """Анализ эвристикой. Возвращает dict:
    complete (bool), confidence [0,1], speech (была ли речь), trailing_silence (с), required_silence (с),
    speech_ms, longest_inner_pause (с), threshold, backend.
    Логика: нужная пауза = max(base, 1.3 * самая длинная внутренняя пауза говорящего), срезается до [0.35, 1.6] с;
    короткая реплика (<0.8 с) и «обрыв» (речь резко кончается на высокой энергии) удлиняют ожидание.
    """
    samples = pcm_to_samples(pcm)
    feats = frame_features(samples)
    res = {"backend": "heuristic", "complete": False, "confidence": 0.0, "speech": False,
           "trailing_silence": 0.0, "required_silence": base_pause, "speech_ms": 0,
           "longest_inner_pause": 0.0, "threshold": 0.0}
    if not feats:
        return res
    vad = HeuristicVAD()
    flags, thr = vad.flags(feats)
    res["threshold"] = round(thr, 1)
    fs = FRAME_MS / 1000.0
    segs = _segments(flags)
    segs = [s for s in segs if (s[1] - s[0]) * fs >= 0.06]  # отбросить микровсплески
    speech_frames = sum(e - s for s, e in segs)
    res["speech_ms"] = int(speech_frames * FRAME_MS)
    if not segs or speech_frames * fs < min_speech:
        res["trailing_silence"] = round(len(feats) * fs, 3)
        return res
    res["speech"] = True
    last_end = segs[-1][1]
    trailing = (len(feats) - last_end) * fs
    inner = [(segs[i + 1][0] - segs[i][1]) * fs for i in range(len(segs) - 1)]
    longest = max(inner) if inner else 0.0
    required = max(base_pause, 1.3 * longest)
    if speech_frames * fs < 0.8:
        required += 0.2
    # обрыв: энергия последних 3 кадров речи близка к максимуму сегмента -> вероятно, не договорил
    seg_s, seg_e = segs[-1]
    energies = [feats[i][0] for i in range(seg_s, seg_e)]
    tail = energies[-3:]
    if len(energies) >= 6 and sum(tail) / len(tail) > 0.8 * max(energies):
        required += 0.25
    required = max(0.35, min(1.6, required))
    res["trailing_silence"] = round(trailing, 3)
    res["required_silence"] = round(required, 3)
    res["longest_inner_pause"] = round(longest, 3)
    complete = trailing >= required
    res["complete"] = complete
    ratio = trailing / required if required else 0.0
    res["confidence"] = round(min(1.0, ratio) if complete or ratio >= 1 else max(0.0, 1.0 - ratio), 3)
    if not complete:
        res["confidence"] = round(max(0.0, 1.0 - ratio), 3)  # уверенность, что ещё не договорил
    return res


# ---------------- ONNX (pipecat Smart Turn v3.x) ----------------
_ONNX = {"session": None, "path": None, "error": None, "np": None}


def _mel_filters(np, sr=16000, n_fft=400, n_mels=80):
    """Whisper-подобный банк mel-фильтров (slaney)."""
    def hz2mel(f):
        f = np.asarray(f, dtype=np.float64)
        lin = f / (200.0 / 3)
        logp = 15.0 + np.log(np.maximum(f, 1e-10) / 1000.0) / (np.log(6.4) / 27.0)
        return np.where(f >= 1000.0, logp, lin)

    def mel2hz(m):
        m = np.asarray(m, dtype=np.float64)
        lin = m * (200.0 / 3)
        logp = 1000.0 * np.exp((np.log(6.4) / 27.0) * (m - 15.0))
        return np.where(m >= 15.0, logp, lin)

    fftfreqs = np.linspace(0, sr / 2, n_fft // 2 + 1)
    mpts = mel2hz(np.linspace(hz2mel(0.0), hz2mel(sr / 2), n_mels + 2))
    fb = np.zeros((n_mels, n_fft // 2 + 1))
    for i in range(n_mels):
        lo, ce, hi = mpts[i], mpts[i + 1], mpts[i + 2]
        up = (fftfreqs - lo) / (ce - lo)
        dn = (hi - fftfreqs) / (hi - ce)
        fb[i] = np.maximum(0, np.minimum(up, dn)) * (2.0 / (hi - lo))
    return fb


def _log_mel(np, audio, seconds=8):
    """Признаки как у Whisper: (80, seconds*100). Аудио: float32 [-1,1], последние `seconds` с, дополнение нулями слева."""
    n = seconds * SAMPLE_RATE
    audio = audio[-n:]
    if len(audio) < n:
        audio = np.concatenate([np.zeros(n - len(audio), dtype=np.float32), audio])
    n_fft, hop = 400, 160
    pad = n_fft // 2
    a = np.pad(audio, (pad, pad), mode="reflect")
    win = np.hanning(n_fft + 1)[:-1].astype(np.float32)
    nfr = 1 + (len(a) - n_fft) // hop
    idx = np.arange(n_fft)[None, :] + hop * np.arange(nfr)[:, None]
    spec = np.abs(np.fft.rfft(a[idx] * win, axis=1)) ** 2
    mel = _mel_filters(np) @ spec[:-1].T
    logm = np.log10(np.maximum(mel, 1e-10))
    logm = np.maximum(logm, logm.max() - 8.0)
    return ((logm + 4.0) / 4.0).astype(np.float32)


def load_onnx(model_path=None):
    """Пробует загрузить ONNX-модель. True/False; причина отказа в onnx_error()."""
    path = model_path or os.environ.get("NOX_SMART_TURN_MODEL")
    _ONNX.update(session=None, path=None, error=None)
    if not path:
        _ONNX["error"] = "model path not set"
        return False
    if not os.path.isfile(path):
        _ONNX["error"] = "model file not found: %s" % path
        return False
    try:
        import numpy as np
        import onnxruntime as ort
    except Exception as e:  # ImportError и пр.
        _ONNX["error"] = "numpy/onnxruntime unavailable: %s" % e
        return False
    try:
        so = ort.SessionOptions()
        so.inter_op_num_threads = 1
        so.intra_op_num_threads = 1
        sess = ort.InferenceSession(path, sess_options=so, providers=["CPUExecutionProvider"])
    except Exception as e:
        _ONNX["error"] = "load failed: %s" % e
        return False
    _ONNX.update(session=sess, path=path, np=np)
    return True


def onnx_error():
    return _ONNX["error"]


def backend():
    """Активный бэкенд: 'onnx' или 'heuristic'."""
    return "onnx" if _ONNX["session"] is not None else "heuristic"


def _onnx_probability(pcm):
    np = _ONNX["np"]
    sess = _ONNX["session"]
    s = pcm_to_samples(pcm)
    audio = np.frombuffer(s.tobytes(), dtype=np.int16).astype(np.float32) / 32768.0
    feats = _log_mel(np, audio)[None, :, :].astype(np.float32)
    name = sess.get_inputs()[0].name
    out = sess.run(None, {name: feats})[0]
    return float(np.asarray(out).reshape(-1)[0])


def analyze(pcm, threshold=0.5):
    """Главная функция. Эвристика всегда считается (нужна для VAD/пауз); при активном ONNX итог берётся из модели,
    но только если после речи есть хотя бы 0.2 с тишины (модель смотрит на конец фразы). Ошибка ONNX -> откат на эвристику."""
    h = heuristic_analyze(pcm)
    if _ONNX["session"] is None or not h["speech"]:
        return h
    try:
        p = _onnx_probability(pcm)
    except Exception as e:
        _ONNX["error"] = "inference failed: %s" % e
        _ONNX["session"] = None
        return h
    h = dict(h)
    h.update(backend="onnx", confidence=round(p, 3), complete=bool(p >= threshold and h["trailing_silence"] >= 0.2),
             model_probability=round(p, 4))
    return h


def is_turn_complete(pcm):
    return analyze(pcm)["complete"]


class TurnDetector:
    """Потоковый вариант: feed(bytes) накапливает буфер (хвост 8 с), update() даёт текущий результат."""

    def __init__(self, max_seconds=8):
        self.buf = bytearray()
        self.max_bytes = max_seconds * SAMPLE_RATE * 2

    def feed(self, chunk):
        self.buf += chunk
        if len(self.buf) > self.max_bytes:
            del self.buf[: len(self.buf) - self.max_bytes]
            if len(self.buf) % 2:
                del self.buf[0]
        return analyze(bytes(self.buf))

    def reset(self):
        self.buf.clear()


if __name__ == "__main__":
    data = sys.stdin.buffer.read()
    print(analyze(data))
