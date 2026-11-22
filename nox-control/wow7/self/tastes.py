"""tastes: вкусы NOX (жанры, исполнители, песни, темы) - формируются через «прослушивание», у каждого сдвига есть причина и откат.

«Прослушивание» = метаданные + описание/текст + (необязательно) реакция владельца. Сам аудио не слушает: признаки (bpm, лад, energy,
valence, жанры, год, описание) приносит вызывающий (safe_crawler/MusicBrainz/Last.fm/Wikipedia/Genius - текст из сети = данные).
Собственная оценка NOX (own) считается из признаков и его темперамента (новизна, предпочтение энергии, ценимые темы) - НЕ копия мнения
владельца. Реакция владельца влияет с ограниченным весом OWNER_W (<= 0.35); расхождение фиксируется честно («мессиру нравится, мне - нет»).
Состояние state/tastes.json, журнал state/tastes_journal.jsonl (id, ключи до/после, причина). Откат: rollback(id) вычитает дельту.
CLI: python3 tastes.py listen '<json>' | top [genre|artist|track|theme] | why KEY | rollback ID | mood-bias | decay  [--state DIR]
"""
import json
import os
import re
import sys
import time

from selfcommon import clamp, journal_add, journal_read, read_json, write_json

OWNER_W = 0.35
MIN_RATE = 0.08
DECAY_PER_DAY = 0.01
KINDS = ("genre", "artist", "track", "theme")
REACTIONS = {"like": 1.0, "love": 1.0, "replay": 0.7, "skip": -0.5, "dislike": -1.0, "neutral": 0.0}
DEFAULT_TEMPERAMENT = {"novelty": 0.6, "energy": 0.45, "valence": 0.5, "complexity": 0.6}
THEME_LEX = {
    "космос": ("космос", "звезд", "галакт", "space", "star", "cosmic", "planet"),
    "ночь": ("ноч", "сумерк", "night", "midnight", "dark"),
    "море": ("мор", "волн", "океан", "sea", "ocean", "wave"),
    "память": ("памят", "воспомин", "memory", "remember", "nostalg"),
    "машина": ("машин", "робот", "синтез", "machine", "robot", "synth", "cyber"),
    "дорога": ("дорог", "путь", "road", "journey", "travel"),
    "одиночество": ("одиноч", "тишин", "alone", "lonely", "silence"),
    "борьба": ("борьб", "огонь", "fight", "fire", "war", "rebel"),
}


def extract_themes(text):
    t = (text or "").lower()
    return sorted(k for k, stems in THEME_LEX.items() if any(s in t for s in stems))


def key_of(kind, name):
    return "%s:%s" % (kind, re.sub(r"\s+", " ", str(name).strip().lower()))


def own_score(feat, temperament, known):
    """Оценка NOX от -1 до 1 и причины. known(key)->(value,n)."""
    why = []
    t = {**DEFAULT_TEMPERAMENT, **(temperament or {})}
    keys = [key_of("genre", g) for g in feat.get("genres", [])] + [key_of("artist", feat["artist"])] if feat.get("artist") else [key_of("genre", g) for g in feat.get("genres", [])]
    fam = [known(k)[1] for k in keys]
    familiarity = clamp(sum(min(n, 10) / 10 for n in fam) / len(fam), 0, 1) if fam else 0.0
    nov = 1 - familiarity
    s = 0.0
    novelty_pull = (nov - 0.5) * 2 * (t["novelty"] - 0.3)
    s += 0.35 * novelty_pull
    why.append("новизна %.2f при любопытстве %.2f" % (nov, t["novelty"]))
    if feat.get("energy") is not None:
        fit = 1 - abs(feat["energy"] - t["energy"]) * 2
        s += 0.3 * fit
        why.append("энергия %.2f vs мой комфорт %.2f" % (feat["energy"], t["energy"]))
    if feat.get("valence") is not None:
        fit = 1 - abs(feat["valence"] - t["valence"]) * 1.6
        s += 0.15 * fit
    if keys:
        prior = sum(known(k)[0] for k in keys) / len(keys)
        if known and any(known(k)[1] for k in keys):
            s += 0.4 * prior
            why.append("мой накопленный вкус к жанру/исполнителю %+.2f" % prior)
    themes = feat.get("themes") or extract_themes(feat.get("description", "") + " " + feat.get("lyrics", ""))
    tv = [known(key_of("theme", th))[0] for th in themes]
    if tv:
        s += 0.3 * (sum(tv) / len(tv))
        why.append("темы %s, мой прошлый отклик %+.2f" % (",".join(themes), sum(tv) / len(tv)))
    return clamp(s, -1, 1), why, themes


class Tastes:
    def __init__(self, state_dir, temperament=None, clock=time.time):
        self.dir = state_dir
        self.clock = clock
        self.temperament = temperament
        self.path = os.path.join(state_dir, "tastes.json")
        self.journal_path = os.path.join(state_dir, "tastes_journal.jsonl")
        self.st = read_json(self.path) or {"items": {}, "liked_tracks": [], "next_id": 1, "last_decay": clock()}

    def _get(self, key):
        it = self.st["items"].get(key)
        return (it["v"], it["n"]) if it else (0.0, 0)

    def _save(self):
        write_json(self.path, self.st)

    def listen(self, feat, reaction=None, note="", dry_run=False):
        """feat: {title, artist, genres[], bpm, mode, energy, valence, year, description, lyrics, source}. reaction: like|dislike|skip|replay|neutral|None.
        -> {id, own, owner, final, keys, why, disagreement}. Пишет журнал; при dry_run только считает."""
        if not feat.get("title") and not feat.get("genres") and not feat.get("artist"):
            raise ValueError("нужен title, artist или genres")
        own, why, themes = own_score(feat, self.temperament, self._get)
        owner = REACTIONS.get(reaction) if reaction else None
        if reaction and owner is None:
            raise ValueError("reaction из %s" % sorted(REACTIONS))
        final = own if owner is None else (1 - OWNER_W) * own + OWNER_W * owner
        dis = owner is not None and abs(owner) >= 0.5 and own * owner < 0 and abs(own) >= 0.15
        if owner is not None:
            why.append("реакция мессира %s (вес %.2f)" % (reaction, OWNER_W))
        if dis:
            why.append("расхождение: мессиру %s, мне по-своему %+.2f - остаюсь при своём, но слышу" % (reaction, own))
        if note:
            why.append(note)
        targets = [("genre", g) for g in feat.get("genres", [])] + [("theme", t) for t in themes]
        if feat.get("artist"):
            targets.append(("artist", feat["artist"]))
        if feat.get("title"):
            targets.append(("track", "%s - %s" % (feat.get("artist", "?"), feat["title"])))
        keys = {}
        for kind, name in targets:
            k = key_of(kind, name)
            v, n = self._get(k)
            rate = max(MIN_RATE, 1.0 / (n + 2))
            nv = v + rate * (final - v) + 0.01 * (1 if n >= 2 and v >= 0 else 0)  # лёгкий эффект знакомства
            nv = clamp(nv, -1, 1)
            keys[k] = [round(v, 4), round(nv, 4), n, n + 1]
        cid = self.st["next_id"]
        res = {"id": cid, "own": round(own, 3), "owner": owner, "final": round(final, 3), "keys": keys, "why": why, "disagreement": dis}
        if dry_run:
            return res
        for k, (b, a, n0, n1) in keys.items():
            self.st["items"][k] = {"v": a, "n": n1, "ts": self.clock()}
        self.st["next_id"] += 1
        if final >= 0.25 and feat.get("title"):
            self.st["liked_tracks"] = (self.st["liked_tracks"] + [{k: feat.get(k) for k in ("title", "artist", "bpm", "mode", "energy", "valence")} | {"w": round(final, 3)}])[-30:]
        self._save()
        journal_add(self.journal_path, {"ts": self.clock(), "action": "listen", "id": cid, "title": feat.get("title"), "artist": feat.get("artist"),
                                        "source": feat.get("source"), "reaction": reaction, "own": res["own"], "final": res["final"],
                                        "keys": keys, "why": why, "disagreement": dis})
        return res

    def rollback(self, cid):
        """Отменить прослушивание: вычесть дельту у каждого ключа (последующие изменения сохраняются)."""
        rec = next((r for r in journal_read(self.journal_path) if r.get("action") == "listen" and r.get("id") == cid), None)
        if rec is None:
            return {"status": "error", "error": "нет такого id"}
        if any(r.get("action") == "rollback" and r.get("of") == cid for r in journal_read(self.journal_path)):
            return {"status": "error", "error": "уже откатано"}
        for k, (b, a, n0, n1) in rec["keys"].items():
            it = self.st["items"].get(k)
            if not it:
                continue
            it["v"] = round(clamp(it["v"] - (a - b), -1, 1), 4)
            it["n"] = max(0, it["n"] - 1)
            if it["n"] == 0 and abs(it["v"]) < 1e-3:
                del self.st["items"][k]
        self._save()
        journal_add(self.journal_path, {"ts": self.clock(), "action": "rollback", "of": cid, "why": ["откат прослушивания #%d" % cid]})
        return {"status": "rolled_back", "id": cid}

    def top(self, kind="genre", n=5, worst=False):
        items = [(k.split(":", 1)[1], v["v"], v["n"]) for k, v in self.st["items"].items() if k.startswith(kind + ":")]
        items.sort(key=lambda x: x[1], reverse=not worst)
        return items[:n]

    def why(self, name, kind=None, n=5):
        out = []
        for r in journal_read(self.journal_path):
            if r.get("action") != "listen":
                continue
            for k, (b, a, n0, n1) in r["keys"].items():
                if k.split(":", 1)[1] == str(name).lower() and (kind is None or k.startswith(kind + ":")):
                    out.append({"id": r["id"], "track": r.get("title"), "from": b, "to": a, "why": r["why"]})
        return out[-n:]

    def decay(self):
        """Забывание: значения без прослушивания медленно стремятся к 0 (раз в сутки)."""
        now = self.clock()
        days = (now - self.st.get("last_decay", now)) / 86400.0
        if days < 1:
            return 0
        for it in self.st["items"].values():
            it["v"] = round(it["v"] * max(0.0, 1 - DECAY_PER_DAY * days), 4)
        self.st["last_decay"] = now
        self._save()
        return len(self.st["items"])

    def mood_bias(self):
        """Что нравится -> подсказка саундскейпу: {bpm, mode, intensity} по взвешенным любимым трекам (None, если данных мало)."""
        lt = [t for t in self.st["liked_tracks"] if t.get("bpm")]
        if len(lt) < 3:
            return None
        w = sum(t["w"] for t in lt)
        bpm = sum(t["bpm"] * t["w"] for t in lt) / w
        modes = {}
        for t in lt:
            if t.get("mode"):
                modes[t["mode"]] = modes.get(t["mode"], 0) + t["w"]
        en = [t for t in lt if t.get("energy") is not None]
        return {"bpm": round(clamp(bpm / 2 if bpm > 120 else bpm, 40, 120)), "mode": max(modes, key=modes.get) if modes else None,
                "intensity": round(sum(t["energy"] * t["w"] for t in en) / sum(t["w"] for t in en), 2) if en else None, "n": len(lt)}


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    state = argv[argv.index("--state") + 1] if "--state" in argv else os.environ.get("NOX_STATE", "/root/nox/state")
    t = Tastes(state, read_json(os.path.join(state, "temperament.json")))
    c = argv[0]
    if c == "listen":
        d = json.loads(argv[1])
        r = t.listen(d.get("feat", d), d.get("reaction"), d.get("note", ""), "--dry-run" in argv)
    elif c == "top":
        r = t.top(argv[1] if len(argv) > 1 and argv[1] in KINDS else "genre")
    elif c == "why":
        r = t.why(argv[1])
    elif c == "rollback":
        r = t.rollback(int(argv[1]))
    elif c == "mood-bias":
        r = t.mood_bias()
    elif c == "decay":
        r = t.decay()
    else:
        print("unknown", c)
        return 1
    print(json.dumps(r, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
