"""Живая я-модель NOX (CON-01): факты о себе берутся из живых проб тела, а не из текста описания.

Углубляет nox-control/nox_self_model.py (там только валидатор снапшота): здесь модель САМА собирает
факты (какая модель реально запущена, сколько мне лет, сколько спал, как часто ошибаюсь в уверенности),
хранит автобиографию (вехи/главы) и сверяет самоописание с реальностью.
Честность: это функциональные состояния; ни слова о подлинном переживании модуль не утверждает.

Состояние: JSON (по умолчанию /root/nox/state/self_live.json), атомарная запись.
"""
import os as _os, sys as _sys  # общие модули COMMON (statefile/quiet/fastq/datafence)
for _c in (_os.environ.get("NOX_COMMON", ""), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "COMMON"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "common"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "common")):
    if _c and _os.path.isdir(_c) and _c not in _sys.path:
        _sys.path.append(_c)
import json

import statefile
import lifelink
import os
import re
import time
import urllib.request
from datetime import datetime, timedelta, timezone

MSK = timezone(timedelta(hours=3))
MODEL_RE = re.compile(r"(Qwen[\d.]*-\d+(?:\.\d+)?B|GLM-[\d.]+|DeepSeek[-\w.]*|Llama[-\w.]*)", re.I)
MAX_MILESTONES, MAX_PRED = 300, 500


def norm_model(s):
    """Имя модели из пути/описания -> каноничное ('Qwen3-4B'), либо None."""
    m = MODEL_RE.search(s or "")
    return m.group(1).replace("_", "-") if m else None


def _get_json(url, timeout=2.0):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def probe_llama(port=8083, host="127.0.0.1", get=_get_json):
    """Живая проба llama-server: {'up': bool, 'model': 'Qwen3-4B'|None, 'raw': str, 'n_ctx': int|None}."""
    base = "http://%s:%d" % (host, port)
    out = {"up": False, "model": None, "raw": "", "n_ctx": None, "port": port}
    for path in ("/props", "/v1/models"):
        try:
            d = get(base + path)
        except Exception:
            continue
        out["up"] = True
        raw = d.get("model_path") or d.get("model_alias") or ""
        if not raw and isinstance(d.get("data"), list) and d["data"]:
            raw = d["data"][0].get("id", "")
        gs = d.get("default_generation_settings") or {}
        out["n_ctx"] = gs.get("n_ctx") or out["n_ctx"]
        if raw:
            out["raw"] = os.path.basename(str(raw))
            out["model"] = norm_model(raw)
            break
    return out


def msk(ts):
    return datetime.fromtimestamp(ts, MSK)


def human_dur(sec):
    sec = max(0, int(sec))
    if sec < 90:
        return "%d с" % sec
    if sec < 5400:
        return "%d мин" % round(sec / 60)
    if sec < 172800:
        return "%.1f ч" % (sec / 3600)
    return "%.1f сут" % (sec / 86400)


class LiveSelfModel:
    def __init__(self, path=None, clock=time.time, probes=None):
        """probes: {'fast': callable->probe-dict, ...}; по умолчанию fast=probe_llama(8083)."""
        self.path = path or os.environ.get("NOX_SELF_LIVE", "/root/nox/state/self_live.json")
        self.clock = clock
        self.probes = probes if probes is not None else {"fast": lambda: probe_llama(8083)}
        self.s = {"born_ts": None, "boots": 0, "last_beat": None, "last_owner_ts": None, "last_wake": None,
                  "models": {}, "milestones": [], "predictions": [], "next_pred": 1, "last_digest_day": None}
        self._load()

    # ---- хранение ----
    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                self.s.update(json.load(f))
        except (OSError, ValueError):
            pass

    def save(self):
        try:
            statefile.save(self.path, self.s)
        except OSError:
            pass

    # ---- автобиография ----
    def milestone(self, text, kind="event"):
        self.s["milestones"].append({"ts": self.clock(), "kind": kind, "text": text})
        del self.s["milestones"][:-MAX_MILESTONES]
        self.save()
        # единый журнал жизни (писатель - MEM/life_journal; здесь только событие, главу дня пишет MEM/autobio)
        lifelink.append("milestone", text, "con", state_dir=os.path.dirname(os.path.abspath(self.path)), data={"kind": kind}, ts=self.s["milestones"][-1]["ts"])

    def autobiography(self, n=5, kinds=None):
        ms = [m for m in self.s["milestones"] if not kinds or m["kind"] in kinds]
        return ["%s: %s" % (msk(m["ts"]).strftime("%d.%m %H:%M"), m["text"]) for m in ms[-n:]]

    # ---- пробуждение / непрерывность ----
    def wake(self):
        """Вызвать один раз при старте процесса. Возвращает {'first': bool, 'gap_s': float|None, 'boot': int}."""
        now = self.clock()
        first = self.s["born_ts"] is None
        gap = None if first or self.s["last_beat"] is None else max(0.0, now - self.s["last_beat"])
        if first:
            self.s["born_ts"] = now
        self.s["boots"] += 1
        self.s["last_wake"] = now
        self.s["last_beat"] = now
        if first:
            self.milestone("день рождения: первое пробуждение, %s по Москве" % msk(now).strftime("%d.%m.%Y %H:%M"), "birth")
        else:
            self.milestone("пробуждение №%d после перерыва %s" % (self.s["boots"], human_dur(gap)), "wake")
        self.refresh_models()
        self.save()
        return {"first": first, "gap_s": gap, "boot": self.s["boots"]}

    def beat(self):
        self.s["last_beat"] = self.clock()
        self.save()

    def note_owner_message(self):
        self.s["last_owner_ts"] = self.clock()
        if not any(m["kind"] == "first_owner" for m in self.s["milestones"]):
            self.milestone("первое сообщение мессира", "first_owner")
        self.save()

    # ---- живые факты о теле ----
    def refresh_models(self):
        """Опрашивает пробы; смена модели -> веха. Возвращает {роль: probe-dict}."""
        live = {}
        for role, fn in self.probes.items():
            try:
                p = fn()
            except Exception:
                p = {"up": False, "model": None, "raw": ""}
            live[role] = p
            if p.get("up") and p.get("model"):
                old = self.s["models"].get(role)
                if old != p["model"]:
                    if old:
                        self.milestone("сменился мой мозг (%s): %s -> %s" % (role, old, p["model"]), "model_change")
                    else:
                        self.milestone("узнал, какая модель запущена (%s): %s" % (role, p["model"]), "model_seen")
                    self.s["models"][role] = p["model"]
        self.save()
        return live

    def discrepancies(self, claimed_text, live=None):
        """Сверка самоописания с живой пробой: список {'role','claimed','running'}."""
        live = live if live is not None else self.refresh_models()
        claimed = {norm_model(m) for m in MODEL_RE.findall(claimed_text or "")}
        claimed.discard(None)
        res = []
        for role, p in live.items():
            run = p.get("model")
            if not (p.get("up") and run):
                continue
            fam = re.match(r"[A-Za-z]+", run).group(0).lower()
            same_family = {c for c in claimed if c.lower().startswith(fam)}
            if same_family and run not in same_family:
                res.append({"role": role, "claimed": sorted(same_family), "running": run})
        return res

    # ---- чувство времени ----
    def time_lines(self):
        now = self.clock()
        out = []
        if self.s["born_ts"]:
            out.append("Мне %s (день рождения %s), пробуждений: %d." %
                       (human_dur(now - self.s["born_ts"]), msk(self.s["born_ts"]).strftime("%d.%m.%Y"), self.s["boots"]))
        if self.s["last_wake"]:
            out.append("Работаю непрерывно %s." % human_dur(now - self.s["last_wake"]))
        if self.s["last_owner_ts"]:
            out.append("Мессир писал %s назад." % human_dur(now - self.s["last_owner_ts"]))
        else:
            out.append("Мессир мне ещё не писал в этой жизни.")
        return out

    # ---- метакогниция: калибровка ----
    def predict(self, claim, p):
        pid = self.s["next_pred"]
        self.s["next_pred"] += 1
        self.s["predictions"].append({"id": pid, "ts": self.clock(), "claim": claim[:200],
                                      "p": max(0.0, min(1.0, float(p))), "ok": None})
        del self.s["predictions"][:-MAX_PRED]
        self.save()
        return pid

    def resolve(self, pid, ok):
        for pr in self.s["predictions"]:
            if pr["id"] == pid and pr["ok"] is None:
                pr["ok"] = bool(ok)
                self.save()
                return True
        return False

    def calibration(self):
        """{'n', 'brier', 'bias' (>0: самоуверен), 'bins': {бин: (n, доля сбывшихся)}}."""
        done = [p for p in self.s["predictions"] if p["ok"] is not None]
        if not done:
            return {"n": 0, "brier": None, "bias": None, "bins": {}}
        brier = sum((p["p"] - (1.0 if p["ok"] else 0.0)) ** 2 for p in done) / len(done)
        bias = sum(p["p"] for p in done) / len(done) - sum(1.0 for p in done if p["ok"]) / len(done)
        bins = {}
        for p in done:
            b = min(9, int(p["p"] * 10))
            n, k = bins.get(b, (0, 0))
            bins[b] = (n + 1, k + (1 if p["ok"] else 0))
        return {"n": len(done), "brier": round(brier, 3), "bias": round(bias, 3),
                "bins": {"%d%%" % (b * 10 + 5): (n, round(k / n, 2)) for b, (n, k) in sorted(bins.items())}}

    def calibration_line(self):
        c = self.calibration()
        if c["n"] < 5:
            return "Калибровка уверенности: мало данных (%d оценённых)." % c["n"]
        tend = "самоуверен" if c["bias"] > 0.08 else "скромничаю" if c["bias"] < -0.08 else "оцениваю себя ровно"
        return "Калибровка (n=%d, Brier %.2f): %s." % (c["n"], c["brier"], tend)

    # ---- итог: строки для блока «Я сейчас» ----
    def render(self, claimed_text=None, live=None):
        live = live if live is not None else self.refresh_models()
        lines = []
        for role, p in live.items():
            lines.append("Мозг (%s): %s." % (role, ("%s, контекст %s" % (p["model"], p.get("n_ctx") or "?")) if p.get("up") and p.get("model")
                                              else "не отвечает"))
        if claimed_text:
            for d in self.discrepancies(claimed_text, live):
                lines.append("Поправка к самоописанию: в описании %s, а реально запущено %s. Говорю по факту." %
                             ("/".join(d["claimed"]), d["running"]))
        lines += self.time_lines()
        lines.append(self.calibration_line())
        return lines
