"""affect_loop: связка drives <-> emotion_pad <-> mood в один живой цикл.

страх растёт -> событие дистресса -> PadState; утоление влечения -> радость; PAD интегрируется в Mood;
Mood сдвигает базу PadState (настроение окрашивает быстрые эмоции). Состояния переживают перезапуск.
Использование (сервер, раз в минуту из nox_bridge/cron):  python3 affect_loop.py tick  (читает сигналы из JSON-файла).
"""
import os as _os, sys as _sys  # общие модули COMMON (statefile/quiet/fastq/datafence)
for _c in (_os.environ.get("NOX_COMMON", ""), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "COMMON"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "common"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "common")):
    if _c and _os.path.isdir(_c) and _c not in _sys.path:
        _sys.path.append(_c)
import json
import os
import sys
import time

import statefile
from appraisal import feel
from drives import Drives
from emotion_pad import PadState
from mood import Mood, memory_salience, quiet_hours


class Affect:
    def __init__(self, state_dir=None, clock=time.time):
        d = state_dir or os.environ.get("NOX_STATE", "/root/nox/state")
        self.clock = clock
        self.dir = d
        self.drives = Drives(path=os.path.join(d, "drives.json"), clock=clock)
        self.mood = Mood(path=os.path.join(d, "mood.json"), clock=clock)
        self.pad_path = os.path.join(d, "pad.json")
        self.pad = PadState(now=clock())
        self._load_pad()
        self.last_emotions = []

    def _load_pad(self):
        try:
            with open(self.pad_path, encoding="utf-8") as f:
                j = json.load(f)
            self.pad.vec, self.pad.ts = tuple(float(x) for x in j["vec"])[:3], float(j["ts"])
        except (OSError, ValueError, KeyError, TypeError):
            pass

    def _save_pad(self):
        try:
            statefile.save(self.pad_path, {"vec": self.pad.vec, "ts": self.pad.ts})
        except OSError:
            pass

    def _apply(self, events, now):
        for ev in events:
            self.pad.apply(ev, now=now)
            self.last_emotions = self.pad.log[-1]["emotions"]

    def on_owner_message(self, text, llm=None, now=None):
        """Сообщение владельца: оценка (LLM/правила) + утоление тяги к разговору. -> результат feel()."""
        now = self.clock() if now is None else now
        res = feel(text, self.pad, llm=llm, now=now)
        self.last_emotions = self.pad.log[-1]["emotions"]
        joy = self.drives.satisfy("bond", 0.6)
        if joy:
            self._apply([joy], now)
        self._save_pad()
        return res

    def on_event(self, event, now=None):
        """Готовое событие/имя из PRESETS (task_done, tool_error ...)."""
        now = self.clock() if now is None else now
        self.pad.apply(event, now=now)
        self.last_emotions = self.pad.log[-1]["emotions"]
        self._save_pad()

    def drain_mind_feed(self):
        """MIND R2: наблюдения/утоления от других процессов (ядро, growth) приходят очередью; drives.json пишет только этот процесс. -> счётчики или None."""
        feed = os.path.join(self.dir, "drives.json.feed.jsonl")
        if not os.path.exists(feed) or os.path.getsize(feed) == 0:
            return None
        try:
            import sys
            r2 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "MIND", "R2")
            if os.path.isdir(r2) and r2 not in sys.path:
                sys.path.append(r2)
            import curiosity
            return curiosity.drain_feed(self.drives, feed)
        except Exception:
            return None

    def tick(self, signals=None, now=None):
        """Один такт: сигналы -> drives -> события -> PAD -> настроение -> база PAD. -> снимок состояния."""
        now = self.clock() if now is None else now
        sig = dict(signals or {})
        self.drain_mind_feed()
        for k, v in self.drives.error_signals().items():
            sig.setdefault(k, v)
        self._apply(self.drives.tick(sig, now=now), now)
        cur = self.pad.value(now)
        self.mood.update(cur, self.drives.level, self.drives.fear, now=now)
        self.pad.baseline = self.mood.baseline(now)
        self._save_pad()
        return self.snapshot(now)

    def snapshot(self, now=None):
        now = self.clock() if now is None else now
        cur = self.pad.value(now)
        quiet = quiet_hours(now)
        ini = None if quiet else self.drives.initiative()       # в тихие часы сам не заговаривает
        return {
            "ts": now, "pad": tuple(round(x, 3) for x in cur),
            "mood": tuple(round(x, 3) for x in self.mood.effective(now)), "mood_label": self.mood.label(now),
            "drives": {k: round(v, 3) for k, v in self.drives.level.items()},
            "fear": {k: round(v, 3) for k, v in self.drives.fear.items()},
            "fear_load": round(self.mood.fear_load, 3), "quiet": quiet,
            "style": self.pad.style(now), "initiative": ini,
            "prompt_lines": self.drives.prompt_lines() + [self.pad.prompt_line(now)],
            "salience": memory_salience(cur, self.last_emotions),
        }


def workspace_signals(snap):
    """Снимок EMO -> сигналы для CON/nox_workspace (единственный рендерер блока «Я сейчас» - Workspace.render_block).
    EMO сам блок НЕ собирает: только поставляет [(key, text, salience, kind)]."""
    sig = [("emo:mood", "Настроение: %s." % snap["mood_label"], min(1.0, 0.25 + abs(snap["mood"][1])), "body")]
    for i, line in enumerate(l for l in snap.get("prompt_lines", []) if l):
        sig.append(("emo:line:%d" % i, line, 0.4, "body"))
    ini = snap.get("initiative")
    if ini:
        sig.append(("emo:initiative", "Хочу сказать сам (если к месту): %s." % ini["text"], 0.5, "body"))
    return sig


def post_to_workspace(ws, snap):
    for key, text, sal, kind in workspace_signals(snap):
        ws.post(key, text, sal, kind)


def main(argv):
    """tick [signals.json] -> печатает снимок; пишет состояние в $NOX_STATE."""
    sig = {}
    if len(argv) > 2:
        with open(argv[2], encoding="utf-8") as f:
            sig = json.load(f)
    a = Affect()
    print(json.dumps(a.tick(sig), ensure_ascii=False))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "tick":
        main(sys.argv)
    else:
        print(__doc__)
