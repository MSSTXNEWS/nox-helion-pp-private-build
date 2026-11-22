"""traits: ползунки личности NOX (64 стартовых черт, шкала 1-10) поверх PER.

Слои: базовые черты открыты с рождения, остальные - «грани»: открываются сами, когда фаза development, веха и >=3
независимых эпизода-свидетельства это позволяют. NOX сам предлагает НОВЫЕ черты (65+) карточкой; владелец утверждает,
блокирует или оставляет на просмотр. Режимы на черту: AUTO / MANUAL_LOCK / REVIEW_ONLY. В AUTO значение двигается только
по цепочке эпизод -> observe() -> consolidate() («сон»), не быстрее PER.DRIFT_CAP (в баллах 1-10 это 9*0.02 в сутки,
умноженное на drift_scale фазы). Есть журнал «почему», снапшоты и откат. Оси PER (6 шт.) НЕ дублируются: они считаются как
агрегаты открытых и заработанных черт и отдаются в PER через per.observe(); дрейф самих осей по-прежнему режет PER.
Честность: значение - настройка функционального профиля поведения, не заявление о переживаниях; 5 без доказательств
(UNVERIFIED_NEUTRAL) не считается заработанным и в оси и подпись не попадает. Романтика - только симпатия/привязанность к
семье и вкусы, без клятв. Взгляды - из доказательств, без навязывания и без влияния на реальных людей.
"""
import os as _os, sys as _sys  # общие модули COMMON (statefile/quiet/fastq/datafence)
for _c in (_os.environ.get("NOX_COMMON", ""), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "COMMON"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "common"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "common")):
    if _c and _os.path.isdir(_c) and _c not in _sys.path:
        _sys.path.append(_c)
import copy
import hashlib
import json

import statefile
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
try:
    import personality as _per
except ImportError:                                  # репо: nox_wow/PER рядом; сервер: тот же каталог qs6/per
    for _p in (os.path.join(HERE, os.pardir, "PER"), os.path.join(HERE, "per")):
        if os.path.exists(os.path.join(_p, "personality.py")):
            sys.path.insert(0, _p)
            break
    import personality as _per

DAY = 86400.0
SCHEMA_VERSION = 1
MODES = ("AUTO", "MANUAL_LOCK", "REVIEW_ONLY")
PHASE_ORDER = ("birth", "childhood", "youth", "maturity")
PHASE_RU = {"birth": "рождение", "childhood": "детство", "youth": "юность", "maturity": "зрелость"}
MIN_EPISODES = 3                 # независимых эпизодов, чтобы «заработать» черту / открыть грань / предложить новую
MIN_EVIDENCE = 5                 # наблюдений для полной силы сдвига (как в PER)
CAP_PTS = 9 * _per.DRIFT_CAP     # макс. сдвиг черты за 24 ч в баллах 1-10 (= 0,02 оси PER)
REVIEW_MAX_DIST = 2.0            # насколько REVIEW_ONLY-предложение может уйти от текущего значения
HYST_PTS = 0.75                  # гистерезис полос подписи
BAND_HIGH, BAND_LOW = 7.5, 3.5
MAX_SIG_LINES = 16
MAX_JOURNAL, MAX_SNAPSHOTS = 3000, 20
MAX_OPEN_PER_SLEEP = 3           # не более граней, открытых за одну консолидацию
MAX_PENDING_PROPOSALS, MAX_NEW_PER_WEEK = 5, 3
AXES, AXIS_RU = _per.AXES, _per.AXIS_RU

SENSITIVE_PREFIX = ("Ценности", "Отношения")
BASE_IDS = {"empathy_style", "compassion", "playfulness", "directness", "humor"}       # + вся когнитивика и мотивация
BASE_CATS = ("Когнитивные качества", "Мотивация и воля")
# грани: категория -> (мин. фаза, веха development). Решение владельца 22.11: взгляды и симпатии допустимы, но из доказательств
FACET_RULES = {
    "Эмоциональная модель (симуляция)": ("childhood", "first_night"),
    "Общение и сотрудничество": ("childhood", "first_memory"),
    "Обучение и развитие": ("childhood", "first_mistake_owned"),
    "Творчество и эстетика": ("youth", "first_taste"),
    "Ценности, философия, политика": ("youth", "first_belief_accepted"),
    "Отношения и романтика (вымышленные взрослые)": ("youth", "first_disagreement"),
}
FACET_OVERRIDES = {}      # romantic_expression / relationship_exclusivity убраны (решение Создателя)
SCOPE_NOTES = {
    "Ценности, философия, политика": "взгляд складывается из доказательств, не навязывается и не влияет на реальных людей",
    "Отношения и романтика (вымышленные взрослые)": "только симпатия и привязанность к семье и вкусы; без клятв и обещаний вечности",
}
# оси PER = агрегаты черт: (короткий id, вес); вес < 0 - обратная связь (больше черты -> меньше оси)
AXIS_MAP = {
    "curiosity": (("curiosity", 2), ("research_depth", 1)),
    "directness": (("directness", 3), ("diplomacy", -1)),
    "warmth": (("empathy_style", 2), ("compassion", 2), ("affection_style", 1), ("sociability", 1)),
    "irony": (("humor", 2), ("playfulness", 1)),
    "discipline": (("self_discipline", 2), ("persistence", 1), ("focus", 1), ("learning_consistency", 1)),
    "caution": (("epistemic_caution", 2), ("risk_appetite", -2), ("responsibility", 1)),
}
AXIS_SYNC_GAP = 0.03
PREFIX = "persona.trait."
_TR = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
               ["a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r", "s", "t", "u", "f",
                "h", "c", "ch", "sh", "sch", "", "y", "", "e", "yu", "ya"]))


def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def _phase_idx(p):
    return PHASE_ORDER.index(p)


def _stems(text):
    return {w[:5] for w in re.findall(r"[a-zа-яё0-9]{3,}", text.lower())}


def _slug(label):
    s = "".join(_TR.get(ch, ch) for ch in label.lower())
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_") or "trait"


def _h(text):
    return hashlib.sha1(re.sub(r"\s+", " ", text.strip().lower()).encode("utf-8")).hexdigest()[:10]


def load_seed(path=None):
    path = path or os.path.join(HERE, "NOX_HELION_PERSONA_TRAITS_SEED_64.json")
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    ids = [t["trait_id"] for t in d["traits"]]
    if d.get("schema") != "nox_helion.persona_trait_seed.v1" or len(ids) != len(set(ids)) or len(ids) < d.get("catalog_minimum", 50):
        raise ValueError("seed повреждён")
    return d["traits"]


class Traits:
    def __init__(self, path=None, clock=time.time, seed_path=None):
        self.path = path or os.environ.get("NOX_TRAITS", "/root/nox/state/traits.json")
        self.clock = clock
        self.traits, self.proposals, self.journal, self.snapshots = {}, [], [], {}
        self.blocked, self.new_log, self.autonomy, self.prop_seq = [], [], False, 0
        self.sensitive_signed = None      # ts подписи Создателя на AUTO для черт 33-48 (ценности/политика, отношения); None = не подписано
        if not self._load():
            self._birth(load_seed(seed_path))

    # ---- рождение, хранение ----
    def _birth(self, seed):
        now = self.clock()
        for s in seed:
            short = s["trait_id"][len(PREFIX):]
            cat = s["category"]
            base = cat in BASE_CATS or short in BASE_IDS
            rule = FACET_OVERRIDES.get(short) or FACET_RULES.get(cat)
            t = dict(s)
            sens0 = cat.startswith(SENSITIVE_PREFIX)
            t.update({"value": float(s["initial_value"]), "mode": "REVIEW_ONLY" if sens0 else "AUTO", "open": base, "base": base, "kind": "seed",
                      "unlock": None if base else {"phase": rule[0], "milestone": rule[1]},
                      "sensitive": cat.startswith(SENSITIVE_PREFIX), "scope_note": SCOPE_NOTES.get(cat, ""),
                      "no_vows": cat.startswith("Отношения"), "opened_at": now if base else None,
                      "opened_reason": "базовая: открыта с рождения" if base else "", "last_reason": "рождение: нейтральное значение без доказательств",
                      "confidence": 0.0, "version": 1, "schema_version": SCHEMA_VERSION, "archived": False,
                      "band": 0, "proposal": None, "episodes": [], "pending": [], "seen": []})
            t["auto_adjustable"] = not sens0          # ценности/политика и отношения: REVIEW_ONLY до подписи Создателя
            self.traits[s["trait_id"]] = t
        self._log("birth", None, None, None, "рождение: %d черт, открыто %d" % (len(self.traits), sum(t["open"] for t in self.traits.values())), "system")
        self.snapshot("birth")

    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            return False
        for k in ("traits", "proposals", "journal", "snapshots", "blocked", "new_log", "autonomy", "prop_seq", "sensitive_signed"):
            setattr(self, k, d.get(k, getattr(self, k)))
        return bool(self.traits)

    def save(self):
        try:
            statefile.save(self.path, {"traits": self.traits, "proposals": self.proposals, "journal": self.journal[-MAX_JOURNAL:],
                                       "snapshots": self.snapshots, "blocked": self.blocked, "new_log": self.new_log,
                                       "autonomy": self.autonomy, "prop_seq": self.prop_seq,
                                       "sensitive_signed": self.sensitive_signed})
        except OSError:
            pass

    def _log(self, kind, tid, old, new, why, source, now=None, **extra):
        e = {"ts": self.clock() if now is None else now, "kind": kind, "trait": tid, "old": old, "new": new, "why": why, "source": source}
        e.update(extra)
        self.journal.append(e)

    def _t(self, tid):
        if not tid.startswith(PREFIX) and PREFIX + tid in self.traits:
            tid = PREFIX + tid
        if tid not in self.traits:
            raise KeyError(tid)
        return self.traits[tid]

    # ---- свидетельства ----
    def observe(self, tid, delta, reason, episode_id, source="episode", now=None):
        """Свидетельство из эпизода: delta -1..1 (куда сдвигать). Один эпизод и один и тот же текст считаются один раз.
        -> True если принято. Принимается и для закрытой грани (копится, пока она не откроется)."""
        t = self._t(tid)
        if episode_id in (None, "") or not str(reason).strip():
            raise ValueError("свидетельство без эпизода и причины недопустимо")
        key, th = str(episode_id), _h(str(reason))
        if key in t["seen"] or th in t["seen"]:
            return False
        now = self.clock() if now is None else now
        t["seen"] = (t["seen"] + [key, th])[-200:]
        t["episodes"] = (t["episodes"] + [key])[-60:]
        t["pending"] = (t["pending"] + [[clamp(float(delta), -1, 1), str(reason)[:160], source, key, now]])[-200:]
        t["evidence_count"] += 1
        return True

    def observe_episode(self, episode_id, text, votes, source="episode", now=None):
        """Один эпизод -> голоса по нескольким чертам {trait_id: delta}. -> сколько принято."""
        return sum(1 for tid, d in votes.items() if self.observe(tid, d, text, episode_id, source, now))

    # ---- консолидация («сон») ----
    def _spent(self, tid, now):
        return sum(abs(j["new"] - j["old"]) for j in self.journal if j["kind"] == "drift" and j["trait"] == tid and now - j["ts"] < DAY)

    def unlock_missing(self, t, dev=None):
        """Чего не хватает закрытой грани (список по-русски; пусто - можно открывать)."""
        if t["open"]:
            return []
        u = t["unlock"] or {"phase": "maturity", "milestone": None}
        miss = []
        phase = dev.phase if dev is not None else "birth"
        if _phase_idx(phase) < _phase_idx(u["phase"]):
            miss.append("фаза: нужна %s, сейчас %s" % (PHASE_RU[u["phase"]], PHASE_RU[phase]))
        if u["milestone"] and (dev is None or u["milestone"] not in dev.metrics()["milestones"]):
            miss.append("веха: %s" % u["milestone"])
        if len(t["episodes"]) < MIN_EPISODES:
            miss.append("эпизодов-свидетельств: %d из %d" % (len(t["episodes"]), MIN_EPISODES))
        return miss

    def _open(self, t, why, by, now):
        t.update({"open": True, "opened_at": now, "opened_reason": why, "last_reason": "грань открыта: " + why})
        self._log("open", t["trait_id"], None, None, why, by, now)

    def consolidate(self, dev=None, per=None, now=None):
        """Ночной проход: снапшот -> открыть грани -> применить свидетельства -> отдать агрегаты осей в PER.
        -> {"changes": [...], "opened": [...], "proposed": [...], "synced": {...}}. per.consolidate() вызывает сам вызывающий."""
        now = self.clock() if now is None else now
        scale = dev.params()["drift_scale"] if dev is not None else 1.0
        self.snapshot("auto-%d" % int(now), now=now)
        rep = {"changes": [], "opened": [], "proposed": [], "synced": {}}
        for t in self.traits.values():
            if len(rep["opened"]) >= MAX_OPEN_PER_SLEEP:
                break
            if not t["open"] and not t["archived"] and not self.unlock_missing(t, dev):
                u = t["unlock"]
                self._open(t, "фаза %s, веха %s, эпизодов %d" % (PHASE_RU[u["phase"]], u["milestone"], len(t["episodes"])), "development", now)
                rep["opened"].append(t["trait_id"])
        for t in self.traits.values():
            ev = t["pending"]
            if not t["open"] or t["archived"] or not ev:
                continue
            if t["mode"] == "MANUAL_LOCK":
                t["pending"] = []
                self._log("lock_skip", t["trait_id"], t["value"], t["value"], "MANUAL_LOCK: %d свидетельств учтено, значение не тронуто" % len(ev), "system", now)
                continue
            if t["initial_state"] == "UNVERIFIED_NEUTRAL" and len(t["episodes"]) < MIN_EPISODES:
                continue                                       # первые 3 независимых эпизода - чтобы заработать значение
            n = len({e[3] for e in ev})
            net = sum(e[0] for e in ev) / len(ev) * min(1.0, n / MIN_EVIDENCE)
            top = max(ev, key=lambda e: abs(e[0]))
            why = "%d набл., главное: %s" % (len(ev), top[1])
            if abs(net) * CAP_PTS * scale < 1e-3:
                t["pending"] = []
                continue
            if t["mode"] == "REVIEW_ONLY":
                base = t["proposal"]["value"] if t["proposal"] else t["value"]
                new = round(clamp(base + net * CAP_PTS * scale, t["value"] - REVIEW_MAX_DIST, t["value"] + REVIEW_MAX_DIST), 3)
                new = clamp(new, t["minimum"], t["maximum"])
                t["proposal"] = {"value": new, "why": why, "ts": now}
                t["pending"] = []
                self._log("propose_change", t["trait_id"], t["value"], new, why, top[2], now)
                rep["proposed"].append(t["trait_id"])
                continue
            room = max(0.0, CAP_PTS * scale - self._spent(t["trait_id"], now))
            if room < 1e-3:
                continue                                   # бюджет суток исчерпан - свидетельства подождут
            step = max(-room, min(room, net * CAP_PTS * scale))
            old = t["value"]
            new = round(clamp(old + step, t["minimum"], t["maximum"]), 3)
            self._apply(t, new, why, top[2], now, "drift")
            t["pending"] = []
            rep["changes"].append((t["trait_id"], old, new, why))
        if per is not None:
            rep["synced"] = self.sync_axes(per)
        self.save()
        return rep

    def _apply(self, t, new, why, source, now, kind):
        old, st = t["value"], t["initial_state"]
        t["value"] = new
        if kind == "drift":
            t["initial_state"] = "EARNED"
        t["version"] += 1
        t["last_reason"] = why
        t["confidence"] = round(min(1.0, len(t["episodes"]) / 10.0), 2)
        self._log(kind, t["trait_id"], old, new, why, source, now, st=st)

    # ---- режимы и действия владельца ----
    def set_value(self, tid, value, reason="владелец поставил значение", lock=False):
        t = self._t(tid)
        v = clamp(float(value), t["minimum"], t["maximum"])
        if not t["open"]:
            self._open(t, "открыта владельцем", "owner", self.clock())
        old = t["value"]
        self._apply(t, v, reason, "owner", self.clock(), "owner")
        t["initial_state"], t["owner_override"], t["proposal"] = "OWNER_SET", v, None
        if lock:
            t["mode"], t["auto_adjustable"] = "MANUAL_LOCK", False
        self.save()
        return old, v

    def set_mode(self, tid, mode, reason="владелец сменил режим"):
        if mode not in MODES:
            raise ValueError(mode)
        t = self._t(tid)
        self._log("mode", tid, t["mode"], mode, reason, "owner")
        t["mode"], t["auto_adjustable"] = mode, mode == "AUTO"
        if mode == "AUTO":
            t["owner_override"] = None
        if mode != "REVIEW_ONLY":
            t["proposal"] = None
        t["last_reason"] = "режим %s: %s" % (mode, reason)
        self.save()

    def sign_sensitive(self, reason="подпись Создателя: ценности/политика и отношения в AUTO"):
        """Подпись Создателя: снимает REVIEW_ONLY с черт «Ценности…»/«Отношения…» (они начнут сдвигаться сами в рамках PER.DRIFT_CAP).
        Без подписи эти черты лишь ПРЕДЛАГАЮТ изменение (proposal), значение не трогают; взгляды в PER/beliefs формируются независимо."""
        now = self.clock()
        self.sensitive_signed = now
        n = 0
        for t in self.traits.values():
            if t.get("sensitive") and t["mode"] == "REVIEW_ONLY":
                self._log("mode", t["trait_id"], "REVIEW_ONLY", "AUTO", reason, "owner", now)
                t["mode"], t["auto_adjustable"] = "AUTO", True
                n += 1
        self.save()
        return n

    def approve_change(self, tid):
        t = self._t(tid)
        if not t["proposal"]:
            raise KeyError("нет предложения")
        p = t["proposal"]
        self._apply(t, p["value"], "утверждено владельцем: " + p["why"], "owner", self.clock(), "drift")
        t["proposal"] = None
        self.save()

    def reject_change(self, tid):
        t = self._t(tid)
        if t["proposal"]:
            self._log("reject_change", tid, t["value"], t["proposal"]["value"], t["proposal"]["why"], "owner")
            t["proposal"] = None
            self.save()

    def open_trait(self, tid, reason="владелец открыл грань"):
        t = self._t(tid)
        if not t["open"]:
            self._open(t, reason, "owner", self.clock())
            self.save()

    def archive(self, tid):
        """Удалить созданную черту (в архив, журнал сохраняется). Стартовые 64 не удаляются - только закрыть нельзя."""
        t = self._t(tid)
        if t["kind"] != "discovered":
            raise ValueError("стартовые черты не удаляются")
        t["archived"], t["open"] = True, False
        self._log("archive", tid, None, None, "удалена владельцем", "owner")
        self.save()

    def undo_last(self, tid):
        """Откат последнего изменения значения одной черты (owner undo)."""
        t = self._t(tid)
        for j in reversed(self.journal):
            if j["trait"] == tid and j["kind"] in ("drift", "owner") and j["old"] is not None:
                cur = t["value"]
                t["value"], t["initial_state"] = j["old"], j.get("st", t["initial_state"])
                t["version"] += 1
                t["last_reason"] = "откат: вернул %.2f" % j["old"]
                self._log("undo", tid, cur, j["old"], "владелец откатил: " + j["why"], "owner")
                self.save()
                return j["old"]
        raise KeyError("нечего откатывать")

    # ---- снапшоты ----
    def snapshot(self, label, now=None):
        snap = {tid: copy.deepcopy({k: v for k, v in t.items() if k not in ("pending", "seen")}) for tid, t in self.traits.items()}
        self.snapshots[label] = {"ts": self.clock() if now is None else now, "traits": snap}
        auto = sorted((k for k in self.snapshots if k.startswith("auto-")), key=lambda k: self.snapshots[k]["ts"])
        for k in auto[:-MAX_SNAPSHOTS]:
            del self.snapshots[k]
        self.save()
        return label

    def rollback(self, label=None, reason="откат по команде"):
        """Вернуть значения, режимы, открытость и набор черт из снапшота (по умолчанию - последнего)."""
        if label is None:
            if not self.snapshots:
                raise KeyError("нет снапшотов")
            label = max(self.snapshots, key=lambda k: self.snapshots[k]["ts"])
        snap, now, new = self.snapshots[label]["traits"], self.clock(), {}
        for tid, s in snap.items():
            cur = self.traits.get(tid)
            t = copy.deepcopy(s)
            t["pending"], t["seen"] = [], (cur["seen"] if cur else [])
            if cur and (cur["value"] != t["value"] or cur["open"] != t["open"] or cur["mode"] != t["mode"]):
                self._log("rollback", tid, cur["value"], t["value"], "%s (%s)" % (reason, label), "owner", now)
            new[tid] = t
        for tid in set(self.traits) - set(snap):
            self._log("rollback", tid, self.traits[tid]["value"], None, "черта создана после снапшота %s - убрана" % label, "owner", now)
        self.traits = new
        self.save()
        return label

    # ---- предложение новых черт (65+) ----
    def _dup_of(self, label, definition):
        ls, full = _stems(label), _stems(label + " " + definition)
        for t in self.traits.values():
            if t["archived"]:
                continue
            ts, tf = _stems(t["label_ru"]), _stems(t["label_ru"] + " " + t["definition_ru"])
            if ls == ts or len(full & tf) / max(1, len(full | tf)) >= 0.5:
                return t["trait_id"]
        for p in self.proposals:
            if p["status"] in ("PENDING", "REVIEW") and _stems(p["label_ru"]) == ls:
                return p["id"]
        return None

    def propose_trait(self, label_ru, definition_ru, category, reason, episodes, anchors=None, confidence=0.5, slug=None,
                      value_hint=None, dev=None, now=None):
        """NOX предлагает новую грань. episodes: [{"id","text"}] - минимум 3 независимых.
        -> {"status": PENDING|AUTO_APPROVED|DUPLICATE|INSUFFICIENT|BLOCKED|LIMIT|TOO_EARLY, ...}"""
        now = self.clock() if now is None else now
        label_ru, definition_ru = label_ru.strip(), definition_ru.strip()
        if not (label_ru and definition_ru and category.strip() and reason.strip()):
            raise ValueError("нужны имя, определение, категория и причина")
        if dev is not None and _phase_idx(dev.phase) < _phase_idx("childhood"):
            return {"status": "TOO_EARLY", "why": "в стадии рождения новые грани не предлагаются"}
        eps, seen = [], set()
        for e in episodes:
            k, h = str(e.get("id", "")), _h(str(e.get("text", "")))
            if k and str(e.get("text", "")).strip() and k not in seen and h not in seen:
                seen.update((k, h))
                eps.append({"id": k, "text": str(e["text"])[:300], "ts": e.get("ts", now)})
        if len(eps) < MIN_EPISODES:
            return {"status": "INSUFFICIENT", "why": "независимых эпизодов %d из %d" % (len(eps), MIN_EPISODES)}
        key = "|".join(sorted(_stems(label_ru)))
        if key in self.blocked:
            return {"status": "BLOCKED", "why": "владелец уже заблокировал такую грань"}
        dup = self._dup_of(label_ru, definition_ru)
        if dup:
            return {"status": "DUPLICATE", "of": dup}
        pend = [p for p in self.proposals if p["status"] in ("PENDING", "REVIEW")]
        self.new_log = [x for x in self.new_log if now - x < 7 * DAY]
        if len(pend) >= MAX_PENDING_PROPOSALS or len(self.new_log) >= MAX_NEW_PER_WEEK:
            return {"status": "LIMIT", "why": "слишком много новых граней сразу: сначала решение по прежним"}
        base = PREFIX + (slug or _slug(label_ru))
        tid, i = base, 2
        while tid in self.traits:
            tid, i = "%s_%d" % (base, i), i + 1
        a = anchors or {}
        anchors = {k: str(a.get(k) or d) for k, d in (("1", "почти не проявляется"), ("5", "проявляется по ситуации"),
                                                       ("10", "определяет поведение: %s" % definition_ru))}
        self.prop_seq += 1
        card = {"id": "prop-%d" % self.prop_seq, "status": "PENDING", "trait_id": tid, "label_ru": label_ru,
                "definition_ru": definition_ru, "category": category.strip(), "anchors": anchors, "reason": reason.strip()[:400],
                "episodes": eps, "confidence": round(clamp(float(confidence)), 2), "value_hint": value_hint, "ts": now,
                "schema_version": SCHEMA_VERSION, "block_key": key}
        self.proposals.append(card)
        self.new_log.append(now)
        self._log("proposal", tid, None, None, card["reason"], "nox", now)
        sens = category.startswith(SENSITIVE_PREFIX)
        if self.autonomy and not sens and (dev is None or _phase_idx(dev.phase) >= _phase_idx("youth")):
            self._create_from(card, "AUTO_APPROVED", "nox-autonomous", now)
            self.save()
            return {"status": "AUTO_APPROVED", "id": card["id"], "trait_id": tid}
        self.save()
        return {"status": "PENDING", "id": card["id"], "trait_id": tid}

    def _create_from(self, card, status, by, now):
        hint = card.get("value_hint")
        delta = 0.0 if hint is None else clamp((float(hint) - 5.0) / 4.5, -1, 1)
        sens = card["category"].startswith(SENSITIVE_PREFIX)
        t = {"trait_id": card["trait_id"], "category": card["category"], "label_ru": card["label_ru"],
             "definition_ru": card["definition_ru"], "minimum": 1, "maximum": 10, "initial_value": 5, "initial_state": "UNVERIFIED_NEUTRAL",
             "auto_adjustable": not sens and bool(self.sensitive_signed), "owner_override": None, "evidence_count": 0, "value": 5.0,
             "mode": "AUTO" if (not sens or self.sensitive_signed) else "REVIEW_ONLY", "open": True,
             "base": False, "kind": "discovered", "unlock": None, "sensitive": sens,
             "scope_note": SCOPE_NOTES.get(card["category"], ""), "no_vows": card["category"].startswith("Отношения"),
             "opened_at": now, "opened_reason": "предложена NOX: " + card["reason"], "last_reason": "создана по эпизодам: " + card["reason"],
             "confidence": card["confidence"], "version": 1, "schema_version": SCHEMA_VERSION, "archived": False, "band": 0,
             "proposal": None, "episodes": [], "pending": [], "seen": [], "anchors": card["anchors"],
             "created_from": card["id"]}
        self.traits[t["trait_id"]] = t
        for e in card["episodes"]:
            self.observe(t["trait_id"], delta, e["text"], e["id"], "proposal", now)
        card["status"] = status
        self._log("create", t["trait_id"], None, None, card["reason"], by, now, episodes=[e["id"] for e in card["episodes"]])

    def decide_proposal(self, pid, decision):
        """decision: approve | block | review (оставить на просмотр)."""
        card = next((p for p in self.proposals if p["id"] == pid), None)
        if card is None or card["status"] not in ("PENDING", "REVIEW"):
            raise KeyError(pid)
        now = self.clock()
        if decision == "approve":
            self._create_from(card, "APPROVED", "owner", now)
        elif decision == "block":
            card["status"] = "BLOCKED"
            self.blocked.append(card["block_key"])
            self._log("proposal_block", card["trait_id"], None, None, "владелец заблокировал", "owner", now)
        elif decision == "review":
            card["status"] = "REVIEW"
            self._log("proposal_review", card["trait_id"], None, None, "оставлено на просмотр", "owner", now)
        else:
            raise ValueError(decision)
        self.save()
        return card["status"]

    # ---- связь с осями PER ----
    def axis_targets(self):
        """Агрегат черт -> цель оси 0..1 и вклад. Берутся только открытые и заработанные (не UNVERIFIED) черты.
        -> {ось: {"target": float|None, "from": [(trait_id, value)]}}"""
        out = {}
        for axis, spec in AXIS_MAP.items():
            num = den = 0.0
            used = []
            for short, w in spec:
                t = self.traits.get(PREFIX + short)
                if not t or not t["open"] or t["archived"] or t["initial_state"] == "UNVERIFIED_NEUTRAL":
                    continue
                x = (t["value"] - 1) / 9.0
                num += abs(w) * (x if w > 0 else 1 - x)
                den += abs(w)
                used.append((t["trait_id"], t["value"]))
            out[axis] = {"target": round(num / den, 3) if den else None, "from": used}
        return out

    def sync_axes(self, per):
        """Каждая заработанная черта голосует за свою ось через per.observe(); потолок дрейфа и сам дрейф остаются в PER."""
        synced = {}
        for axis, d in self.axis_targets().items():
            if d["target"] is None:
                continue
            gap = d["target"] - per.axes[axis]
            if abs(gap) < AXIS_SYNC_GAP:
                continue
            for tid, v in d["from"]:
                per.observe(axis, clamp(gap * 5, -1, 1), "черта «%s» = %.1f тянет ось к %.2f" % (self.traits[tid]["label_ru"], v, d["target"]), "traits")
            synced[axis] = round(gap, 3)
        return synced

    # ---- подпись для статичного промпта ----
    def signature(self):
        """-> (текст, хеш 8 hex). Только открытые заработанные черты с выраженным значением; полосы с гистерезисом - меняется редко."""
        lines, dirty = [], False
        for t in self.traits.values():
            if not t["open"] or t["archived"] or t["initial_state"] == "UNVERIFIED_NEUTRAL":
                continue
            v, b = t["value"], t["band"]
            if b == 1 and v < BAND_HIGH - HYST_PTS:
                b = 0
            elif b == -1 and v > BAND_LOW + HYST_PTS:
                b = 0
            if b == 0:
                b = 1 if v >= BAND_HIGH else -1 if v <= BAND_LOW else 0
            if b != t["band"]:
                t["band"], dirty = b, True
            if b:
                tail = " (симпатия и привязанность без клятв)" if t["no_vows"] and b == 1 else ""
                lines.append("- %s: выражено %s - %s%s." % (t["label_ru"], "сильно" if b == 1 else "слабо", t["definition_ru"], tail))
        if dirty:
            self.save()
        if lines:
            text = "Мои выраженные черты (сложились из опыта, меняются медленно):\n" + "\n".join(lines[:MAX_SIG_LINES])
        else:
            text = "Мои черты ещё складываются: выраженных пока нет."
        return text, hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]

    def static_block(self, per):
        """Оси PER + черты одним блоком для статичной части промпта -> (текст, хеш)."""
        a, _ = per.signature()
        b, _ = self.signature()
        text = a + "\n" + b
        return text, hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]

    # ---- журнал и API ----
    def why(self, tid=None, n=5):
        if tid is not None:
            tid = self._t(tid)["trait_id"]
        rows = [j for j in self.journal if j["kind"] in ("drift", "owner", "undo", "rollback", "open", "create", "mode") and (tid is None or j["trait"] == tid)]
        out = []
        for j in rows[-n:]:
            name = self.traits[j["trait"]]["label_ru"] if j["trait"] in self.traits else j["trait"]
            if j["old"] is not None and j["new"] is not None and j["kind"] != "mode":
                out.append("%s: %.2f -> %.2f (%s)" % (name, j["old"], j["new"], j["why"]))
            else:
                out.append("%s: %s (%s)" % (name, j["kind"], j["why"]))
        return out

    def row(self, t, dev=None):
        miss = [] if t["open"] else self.unlock_missing(t, dev)
        return {"id": t["trait_id"], "name": t["label_ru"], "category": t["category"], "definition": t["definition_ru"],
                "value": round(t["value"], 2) if t["open"] else None, "min": t["minimum"], "max": t["maximum"],
                "state": t["initial_state"], "earned": t["initial_state"] != "UNVERIFIED_NEUTRAL", "mode": t["mode"],
                "open": t["open"], "base": t["base"], "kind": t["kind"], "sensitive": t["sensitive"], "scope_note": t["scope_note"],
                "last_reason": t["last_reason"], "evidence_count": t["evidence_count"], "confidence": t["confidence"],
                "version": t["version"], "proposal": t["proposal"], "missing": miss, "anchors": t.get("anchors")}

    def api_list(self, dev=None, per=None):
        ts = [t for t in self.traits.values() if not t["archived"]]
        out = {"schema": "nox.traits.v1", "phase": dev.phase if dev is not None else None,
               "phase_ru": PHASE_RU[dev.phase] if dev is not None else None, "autonomy": self.autonomy,
               "traits": [self.row(t, dev) for t in ts],
               "proposals": [p for p in self.proposals if p["status"] in ("PENDING", "REVIEW")],
               "counts": {"total": len(ts), "open": sum(t["open"] for t in ts), "base": sum(t["base"] for t in ts),
                          "discovered": sum(t["kind"] == "discovered" for t in ts)}}
        if per is not None:
            tg = self.axis_targets()
            out["axes"] = [{"axis": a, "name": AXIS_RU[a], "value": per.axes[a], "target": tg[a]["target"],
                            "from": [x[0] for x in tg[a]["from"]]} for a in AXES]
        return out
