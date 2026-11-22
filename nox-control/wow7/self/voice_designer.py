"""voice_designer: NOX сам проектирует и меняет свой мужской голос; каждое изменение - с причиной в журнале.

Голос = VoiceSpec (числа: высота, темп, яркость, шумность/дыхание, тепло) + выбор бэкенда + рецепт.
Решение зависит от настроения PAD (p,a,d), фазы развития и ночи; есть якорь идентичности (голос узнаваем:
отклонение от базы ограничено), гистерезис (не чаще MIN_DWELL_S), шаг изменения ограничен (плавно), откат.

Бэкенды (лицензии/язык проверены по карточкам HF, ноябрь 2026; "чужие данные", перепроверять перед коммерцией):
  silero_ru   - Silero v5 ru (aidar/eugene), RU да; лицензия CC BY-NC-SA 4.0 (не коммерч.) - уже в WOW/voice_server.py
  kokoro_mix  - Kokoro-82M, Apache-2.0, смешивание голосов = взвешенная сумма голос-тензоров; русского в карточке нет -> es/en
  parler_ref  - Parler-TTS mini v1.1, Apache-2.0, описание голоса текстом, ТОЛЬКО английский -> используется для
                генерации англ. референса/проб, не для русской речи
  espeech_clone - ESpeech-TTS (F5-архитектура, ru), Apache-2.0, клон по референсу <=12 с + транскрипт
  f5_ru_clone - hotstone228/F5-TTS-Russian, CC-BY-NC-SA-4.0 (не коммерч.), клон по референсу
  xtts_clone  - Coqui XTTS-v2, CPML (не коммерч.), RU да; уже есть в voice/tts_server.py
Рецепт для русского (честно): референс -> клон. Референс получают из silero_ru (aidar/eugene) + ffmpeg-цепочка
(сдвиг высоты/тембра, build_ffmpeg_filter), затем клон ESpeech/F5-RU/XTTS на этом референсе: так NOX получает
СВОЙ тембр, а не тембр готового диктора. Журнал: JSONL state/voice_journal.jsonl; текущий профиль state/voice_profile.json.
CLI: python3 voice_designer.py decide --mood p,a,d --phase adult [--night] [--state DIR] [--dry-run]
     python3 voice_designer.py show|why|rollback [--state DIR] | recipe
"""
import json
import os
import sys
import time
from dataclasses import dataclass, asdict, field

from selfcommon import clamp, journal_add, journal_read, read_json, write_json

MIN_DWELL_S = 1800
MAX_STEP = {"pitch_st": 1.0, "rate": 0.06, "bright": 0.15, "breath": 0.10, "warmth": 0.15}
PHASES = ("newborn", "young", "adult", "elder")
# База по фазе: чем старше - тем ниже и медленнее; значения - гипотеза, подбирать на слух/A-B.
PHASE_BASE = {
    "newborn": dict(pitch_st=1.5, rate=1.08, bright=0.65, breath=0.10, warmth=0.45),
    "young":   dict(pitch_st=0.5, rate=1.03, bright=0.55, breath=0.08, warmth=0.55),
    "adult":   dict(pitch_st=-1.0, rate=1.00, bright=0.50, breath=0.06, warmth=0.65),
    "elder":   dict(pitch_st=-2.0, rate=0.94, bright=0.42, breath=0.12, warmth=0.75),
}
# якорь идентичности: допустимый разброс вокруг базы фазы (голос остаётся узнаваемым)
BAND = {"pitch_st": 1.5, "rate": 0.10, "bright": 0.20, "breath": 0.10, "warmth": 0.20}
RANGE = {"pitch_st": (-4.0, 3.0), "rate": (0.82, 1.20), "bright": (0.0, 1.0), "breath": (0.0, 0.4), "warmth": (0.0, 1.0)}

BACKENDS = {
    "silero_ru": dict(lang=("ru",), license="CC-BY-NC-SA-4.0", commercial=False, mode="native", hf="snakers4/silero-models"),
    "kokoro_mix": dict(lang=("en", "es"), license="Apache-2.0", commercial=True, mode="mix", hf="hexgrad/Kokoro-82M"),
    "parler_ref": dict(lang=("en",), license="Apache-2.0", commercial=True, mode="describe", hf="parler-tts/parler-tts-mini-v1.1"),
    "espeech_clone": dict(lang=("ru",), license="Apache-2.0", commercial=True, mode="clone", hf="ESpeech/ESpeech-TTS-1_SFT-256K"),
    "f5_ru_clone": dict(lang=("ru",), license="CC-BY-NC-SA-4.0", commercial=False, mode="clone", hf="hotstone228/F5-TTS-Russian"),
    "xtts_clone": dict(lang=("ru", "es", "en"), license="CPML", commercial=False, mode="clone", hf="coqui/XTTS-v2"),
}
KOKORO_MALE = ("em_alex", "em_santa", "am_michael", "am_adam", "bm_george")


@dataclass
class VoiceSpec:
    pitch_st: float
    rate: float
    bright: float
    breath: float
    warmth: float
    backend: str = "silero_ru"
    base_speaker: str = "aidar"
    kokoro_mix: dict = field(default_factory=dict)
    phase: str = "adult"

    def numbers(self):
        return {k: getattr(self, k) for k in MAX_STEP}


def base_spec(phase):
    if phase not in PHASE_BASE:
        raise ValueError("phase must be one of %s" % (PHASES,))
    return VoiceSpec(phase=phase, **PHASE_BASE[phase])


def target_numbers(mood, phase, night=False):
    """-> (числа, причины). mood=(p,a,d) в [-1,1]. Все числа внутри полосы вокруг базы фазы."""
    p, a, d = (clamp(float(x), -1, 1) for x in mood)
    b = PHASE_BASE[phase]
    why = []
    t = dict(b)
    t["pitch_st"] += 0.8 * a - 0.6 * d * 0.5 + 0.4 * p
    t["rate"] += 0.07 * a - 0.03 * (1 if p < -0.3 else 0)
    t["bright"] += 0.2 * p + 0.1 * a
    t["breath"] += 0.06 * max(0.0, -p) + 0.04 * max(0.0, -a)
    t["warmth"] += 0.12 * p - 0.05 * a + 0.05 * d
    if a > 0.35:
        why.append("возбуждение %+.2f -> выше и быстрее" % a)
    if a < -0.35:
        why.append("спад энергии %+.2f -> тише темп, больше дыхания" % a)
    if p > 0.35:
        why.append("радость %+.2f -> ярче и теплее" % p)
    if p < -0.35:
        why.append("печаль %+.2f -> глуше и ниже яркость" % p)
    if d > 0.4:
        why.append("уверенность %+.2f -> чуть ниже, ровнее" % d)
    if night:
        t["rate"] -= 0.06
        t["pitch_st"] -= 0.5
        t["bright"] -= 0.1
        t["breath"] += 0.05
        why.append("ночь -> тише, медленнее, мягче")
    out = {}
    for k, v in t.items():
        lo = max(RANGE[k][0], b[k] - BAND[k])
        hi = min(RANGE[k][1], b[k] + BAND[k])
        out[k] = round(clamp(v, lo, hi), 3)
    if not why:
        why.append("спокойное ровное состояние -> база фазы %s" % phase)
    return out, why


def pick_backend(lang="ru", allow_noncommercial=True, installed=None):
    """Порядок для русского: клон на нашем референсе (если установлен), иначе silero. installed - множество доступных."""
    order = {"ru": ["espeech_clone", "f5_ru_clone", "xtts_clone", "silero_ru"],
             "es": ["kokoro_mix", "xtts_clone"], "en": ["kokoro_mix", "parler_ref"]}[lang]
    for name in order:
        meta = BACKENDS[name]
        if not allow_noncommercial and not meta["commercial"]:
            continue
        if installed is not None and name not in installed:
            continue
        return name
    return None


def kokoro_mix_weights(spec, voices=KOKORO_MALE[:2]):
    """Смесь двух мужских голосов Kokoro: яркость -> доля более светлого. Сумма весов = 1."""
    w = round(clamp(spec.bright, 0.0, 1.0), 2)
    return {voices[0]: round(1 - w, 2), voices[1]: w}


def kokoro_voice_string(mix):
    return ",".join("%s*%s" % (k, v) for k, v in mix.items() if v > 0)


def build_ffmpeg_filter(spec, sr=24000):
    """Цепочка для генерации референса из базового диктора: высота через asetrate+atempo-компенсацию, тембр EQ."""
    ratio = 2 ** (spec.pitch_st / 12.0)
    tempo = clamp(1.0 / ratio * spec.rate, 0.5, 2.0)
    low_gain = round(-3 + 6 * spec.warmth, 1)      # 120 Гц: тепло
    high_gain = round(-6 + 10 * spec.bright, 1)    # 4.5 кГц: яркость
    return ("asetrate=%d,aresample=%d,atempo=%.4f,equalizer=f=120:t=h:w=150:g=%s,equalizer=f=4500:t=h:w=2000:g=%s"
            % (round(sr * ratio), sr, tempo, low_gain, high_gain))


def parler_description(spec):
    """Английское описание для Parler-TTS (только для референса/проб; Parler не говорит по-русски)."""
    pitch = "low-pitched" if spec.pitch_st < -1.2 else "moderately low-pitched" if spec.pitch_st < 0.3 else "mid-pitched"
    speed = "slowly" if spec.rate < 0.96 else "at a moderate pace" if spec.rate < 1.06 else "fairly fast"
    tone = "warm and soft" if spec.warmth > 0.6 else "neutral" if spec.warmth > 0.4 else "cool and crisp"
    clar = "very clear audio" if spec.breath < 0.1 else "slightly breathy, close-up recording"
    return "A man with a %s, %s voice speaks %s, %s, with very little reverberation." % (pitch, tone, speed, clar)


class VoiceDesigner:
    def __init__(self, state_dir, lang="ru", allow_noncommercial=True, installed=None, clock=time.time):
        self.dir = state_dir
        self.lang = lang
        self.allow_nc = allow_noncommercial
        self.installed = installed
        self.clock = clock
        self.profile_path = os.path.join(state_dir, "voice_profile.json")
        self.journal_path = os.path.join(state_dir, "voice_journal.jsonl")

    def current(self):
        d = read_json(self.profile_path)
        return VoiceSpec(**d["spec"]) if d else None

    def _spec_from(self, nums, phase, backend):
        s = VoiceSpec(phase=phase, backend=backend or "silero_ru", **nums)
        if s.backend == "kokoro_mix":
            s.kokoro_mix = kokoro_mix_weights(s)
        elif s.backend == "silero_ru":
            s.base_speaker = "aidar" if s.pitch_st < 0 else "eugene"
        return s

    def decide(self, mood, phase="adult", night=False, force=False, dry_run=False):
        """Один шаг: целевой голос -> плавно (MAX_STEP) -> запись профиля + журнал причины. Возвращает dict-решение."""
        now = self.clock()
        cur_d = read_json(self.profile_path)
        target, why = target_numbers(mood, phase, night)
        backend = pick_backend(self.lang, self.allow_nc, self.installed)
        if backend is None:
            return {"changed": False, "reason": "нет доступного бэкенда для %s (лицензия/установка)" % self.lang}
        if cur_d and not force and now - cur_d["ts"] < MIN_DWELL_S and cur_d["spec"]["phase"] == phase:
            return {"changed": False, "reason": "гистерезис: голос держится %d с" % MIN_DWELL_S}
        cur = cur_d["spec"] if cur_d else None
        nums = {}
        for k, tv in target.items():
            if cur and cur["phase"] == phase:
                tv = cur[k] + clamp(tv - cur[k], -MAX_STEP[k], MAX_STEP[k])
            nums[k] = round(tv, 3)
        spec = self._spec_from(nums, phase, backend)
        if cur and all(abs(cur[k] - nums[k]) < 1e-6 for k in nums) and cur["backend"] == spec.backend:
            return {"changed": False, "reason": "без изменений"}
        rec = {"ts": now, "action": "decide", "mood": list(mood), "phase": phase, "night": night, "why": why,
               "before": cur, "after": asdict(spec), "backend": spec.backend, "license": BACKENDS[spec.backend]["license"]}
        if not dry_run:
            write_json(self.profile_path, {"ts": now, "spec": asdict(spec), "ffmpeg": build_ffmpeg_filter(spec),
                                           "parler_description": parler_description(spec),
                                           "voice_server": self.export_for_server(spec)})
            journal_add(self.journal_path, rec)
        return {"changed": True, "spec": asdict(spec), "why": why}

    @staticmethod
    def export_for_server(spec):
        """Поля, которые WOW/voice_server.py/клиент берут: скорость, speaker, смесь Kokoro."""
        d = {"backend": spec.backend, "speed": spec.rate}
        if spec.backend == "kokoro_mix":
            d["voice"] = kokoro_voice_string(spec.kokoro_mix)
        elif spec.backend == "silero_ru":
            d["speaker"] = spec.base_speaker
        return d

    def rollback(self, dry_run=False):
        """Вернуть предыдущий голос из журнала (ищет последнее 'decide' с before != None)."""
        for rec in reversed(journal_read(self.journal_path)):
            if rec.get("action") == "decide" and rec.get("before"):
                spec = VoiceSpec(**rec["before"])
                now = self.clock()
                if not dry_run:
                    write_json(self.profile_path, {"ts": now, "spec": asdict(spec), "ffmpeg": build_ffmpeg_filter(spec),
                                                   "parler_description": parler_description(spec),
                                                   "voice_server": self.export_for_server(spec)})
                    journal_add(self.journal_path, {"ts": now, "action": "rollback", "why": ["откат к прошлому голосу"],
                                                    "after": asdict(spec)})
                return {"rolled_back": True, "spec": asdict(spec)}
        return {"rolled_back": False, "reason": "нет предыдущего голоса"}

    def why(self, n=5):
        return [{"ts": r["ts"], "action": r["action"], "why": r.get("why")} for r in journal_read(self.journal_path, last=n)]


RECIPE = [
    "1. Референс: silero_ru (aidar/eugene) -> ffmpeg -i base.wav -af '<build_ffmpeg_filter>' ref.wav (8-12 с чистой речи).",
    "2. Транскрипт референса (STT faster-whisper уже есть в voice/stt_server.py).",
    "3. Клон: espeech_clone (Apache-2.0) или f5_ru_clone/xtts_clone (не коммерч.) с ref.wav+транскриптом.",
    "4. Ночью/в сильных состояниях меняются числа и фильтр, референс пересоздаётся не чаще раза в сутки.",
    "5. Английские пробы (описание тембра): Parler-TTS mini v1.1 с parler_description - для выбора тембра на слух, не для речи RU.",
]


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    state = argv[argv.index("--state") + 1] if "--state" in argv else os.environ.get("NOX_STATE", "/root/nox/state")
    vd = VoiceDesigner(state)
    cmd = argv[0]
    dry = "--dry-run" in argv
    if cmd == "decide":
        mood = tuple(float(x) for x in argv[argv.index("--mood") + 1].split(","))
        phase = argv[argv.index("--phase") + 1] if "--phase" in argv else "adult"
        print(json.dumps(vd.decide(mood, phase, "--night" in argv, "--force" in argv, dry), ensure_ascii=False, indent=1))
    elif cmd == "show":
        print(json.dumps(read_json(vd.profile_path), ensure_ascii=False, indent=1))
    elif cmd == "why":
        print(json.dumps(vd.why(), ensure_ascii=False, indent=1))
    elif cmd == "rollback":
        print(json.dumps(vd.rollback(dry), ensure_ascii=False, indent=1))
    elif cmd == "recipe":
        print("\n".join(RECIPE))
    else:
        print("unknown", cmd)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
