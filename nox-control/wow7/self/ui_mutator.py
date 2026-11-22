"""ui_mutator: NOX сам предлагает и применяет изменения внешнего вида веба «Резонанс» - безопасно.

Принципы: (1) белый список CSS-переменных с типами и диапазонами (никакого произвольного CSS, url(), @import, селекторов);
(2) анимации только из каталога (pulse/breathe/drift/none) с ограниченными параметрами; (3) контраст текста/фона >= 4.5 (WCAG);
(4) мелкое (малые сдвиги, <= MINOR_MAX_VARS переменных) применяется сам в режиме ПРОБЫ с TTL - не подтверждено/ухудшилось -> авто-откат;
    глобальное (смена темы, большой сдвиг цвета, много переменных) - только после согласия владельца (pending -> approve/reject);
(5) каждая версия хранится, откат на любую; журнал «почему»; файл ui_overrides.css генерируется из состояния (песочница = отдельный
    файл, подключается <link> после основной темы; удалить файл = исходный вид). Тема из EMO/mood_ui.py (HELION...) - база; мутатор
    лишь накладывает переопределения поверх.
CLI: python3 ui_mutator.py propose '<json>' | approve ID | reject ID | confirm | tick | rollback [VERSION] | show | css  [--state DIR]
"""
import colorsys
import json
import os
import re
import sys
import time

from selfcommon import clamp, journal_add, journal_read, read_json, write_json

TRIAL_TTL_S = 900
MINOR_MAX_VARS = 3
MINOR_MAX_HUE_SHIFT = 25.0
MINOR_MAX_LIGHT_SHIFT = 0.08
MINOR_MAX_REL = 0.25
MAX_VERSIONS = 50

# имя переменной -> (тип, мин, макс, по умолчанию, глобальная?)
WHITELIST = {
    "--nox-accent":      ("color", None, None, "#d9a441", False),
    "--nox-accent-2":    ("color", None, None, "#6aa7c9", False),
    "--nox-bg":          ("color", None, None, "#0b0f14", True),
    "--nox-surface":     ("color", None, None, "#131a22", True),
    "--nox-text":        ("color", None, None, "#e8e6e1", True),
    "--nox-muted":       ("color", None, None, "#9aa4ad", False),
    "--nox-glow":        ("num", 0.0, 1.0, 0.4, False),
    "--nox-radius":      ("px", 0, 24, 10, True),
    "--nox-blur":        ("px", 0, 30, 8, False),
    "--nox-anim-speed":  ("num", 0.4, 2.0, 1.0, False),
    "--nox-font-scale":  ("num", 0.9, 1.15, 1.0, True),
    "--nox-line-height": ("num", 1.3, 1.8, 1.5, True),
    "--nox-planet-opacity": ("num", 0.0, 1.0, 0.8, False),
}
ANIMATIONS = {  # имя -> (--nox-anim-name, диапазон периода, с)
    "none": None,
    "pulse": (2.0, 12.0),
    "breathe": (3.0, 16.0),
    "drift": (10.0, 120.0),
}
HEX = re.compile(r"^#([0-9a-fA-F]{6})$")
HSL = re.compile(r"^hsl\(\s*(\d{1,3})(?:deg)?\s*,\s*(\d{1,3})%\s*,\s*(\d{1,3})%\s*\)$")
PX = re.compile(r"^(\d{1,3})(?:px)?$")
FORBIDDEN = re.compile(r"url\(|@import|expression|javascript:|behavior|</?style|[{};<>\\]|/\*", re.I)


class Rejected(ValueError):
    pass


def parse_color(v):
    if not isinstance(v, str) or FORBIDDEN.search(v):
        raise Rejected("недопустимый цвет: %r" % (v,))
    m = HEX.match(v)
    if m:
        h = m.group(1)
        return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    m = HSL.match(v)
    if m and int(m.group(1)) <= 360 and int(m.group(2)) <= 100 and int(m.group(3)) <= 100:
        return colorsys.hls_to_rgb(int(m.group(1)) / 360, int(m.group(3)) / 100, int(m.group(2)) / 100)
    raise Rejected("цвет только #rrggbb или hsl(h,s%%,l%%): %r" % (v,))


def to_hex(rgb):
    return "#%02x%02x%02x" % tuple(round(clamp(c, 0, 1) * 255) for c in rgb)


def _lin(c):
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def luminance(rgb):
    r, g, b = (_lin(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def validate_value(name, value):
    """-> нормализованное значение (строка для CSS). Бросает Rejected."""
    if name not in WHITELIST:
        raise Rejected("переменная не в белом списке: %s" % name)
    kind, lo, hi, _, _ = WHITELIST[name]
    if kind == "color":
        return to_hex(parse_color(value))
    if isinstance(value, bool):
        raise Rejected("число ожидалось: %s" % name)
    if kind == "num":
        try:
            x = float(value)
        except (TypeError, ValueError):
            raise Rejected("число ожидалось: %s=%r" % (name, value))
        if not lo <= x <= hi:
            raise Rejected("%s вне диапазона [%s,%s]: %s" % (name, lo, hi, x))
        return repr(round(x, 3)).rstrip("0").rstrip(".") if "." in repr(round(x, 3)) else repr(round(x, 3))
    if kind == "px":
        if isinstance(value, (int, float)):
            x = float(value)
        else:
            m = PX.match(str(value).strip())
            if not m:
                raise Rejected("px ожидалось: %s=%r" % (name, value))
            x = float(m.group(1))
        if not lo <= x <= hi:
            raise Rejected("%s вне диапазона [%s,%s]: %s" % (name, lo, hi, x))
        return "%dpx" % round(x)
    raise Rejected("неизвестный тип")


def check_contrast(vars_):
    text, bg, surf = vars_.get("--nox-text"), vars_.get("--nox-bg"), vars_.get("--nox-surface")
    for lab, other in (("bg", bg), ("surface", surf)):
        if text and other and contrast(parse_color(text), parse_color(other)) < 4.5:
            raise Rejected("контраст текст/%s < 4.5" % lab)
    muted = vars_.get("--nox-muted")
    if muted and bg and contrast(parse_color(muted), parse_color(bg)) < 3.0:
        raise Rejected("контраст muted/bg < 3.0")


def validate(change):
    """change: {"vars": {...}, "animation": {"name":..., "period_s":...}|None}. -> нормализованный dict (или Rejected)."""
    if not isinstance(change, dict):
        raise Rejected("изменение должно быть объектом")
    extra = set(change) - {"vars", "animation", "theme"}
    if extra:
        raise Rejected("лишние поля: %s" % sorted(extra))
    out = {"vars": {}}
    for k, v in (change.get("vars") or {}).items():
        out["vars"][k] = validate_value(k, v)
    anim = change.get("animation")
    if anim is not None:
        name = anim.get("name") if isinstance(anim, dict) else None
        if name not in ANIMATIONS:
            raise Rejected("анимация только из %s" % sorted(ANIMATIONS))
        if ANIMATIONS[name]:
            lo, hi = ANIMATIONS[name]
            try:
                per = float(anim.get("period_s"))
            except (TypeError, ValueError):
                raise Rejected("period_s обязателен")
            if not lo <= per <= hi:
                raise Rejected("period_s для %s в [%s,%s]" % (name, lo, hi))
            out["animation"] = {"name": name, "period_s": round(per, 2)}
        else:
            out["animation"] = {"name": "none", "period_s": 0}
    if "theme" in change:
        if change["theme"] not in ("HELION", "CHRONOS", "SOMNIUM", "FORGE", "SYNAPSE"):
            raise Rejected("тема из EMO/mood_ui.py")
        out["theme"] = change["theme"]
    if not out["vars"] and "animation" not in out and "theme" not in out:
        raise Rejected("пустое изменение")
    return out


def classify(norm, current_vars):
    """-> ('minor'|'global', причины). Глобальное - требует согласия владельца."""
    why = []
    if "theme" in norm:
        why.append("смена темы")
    vs = norm["vars"]
    if len(vs) > MINOR_MAX_VARS:
        why.append("переменных больше %d" % MINOR_MAX_VARS)
    for k, v in vs.items():
        if WHITELIST[k][4]:
            why.append("%s затрагивает всю раскладку/читаемость" % k)
        old = current_vars.get(k, WHITELIST[k][3] if WHITELIST[k][0] == "color" else None)
        if WHITELIST[k][0] == "color" and old:
            ho, lo_, so = colorsys.rgb_to_hls(*parse_color(old))
            hn, ln, sn = colorsys.rgb_to_hls(*parse_color(v))
            dh = min(abs(hn - ho), 1 - abs(hn - ho)) * 360
            if dh > MINOR_MAX_HUE_SHIFT or abs(ln - lo_) > MINOR_MAX_LIGHT_SHIFT:
                why.append("%s: большой сдвиг цвета" % k)
        elif WHITELIST[k][0] in ("num", "px"):
            lo, hi = WHITELIST[k][1], WHITELIST[k][2]
            oldv = float(str(current_vars.get(k, WHITELIST[k][3])).replace("px", ""))
            newv = float(v.replace("px", ""))
            if abs(newv - oldv) > MINOR_MAX_REL * (hi - lo):
                why.append("%s: сдвиг > %d процентов диапазона" % (k, MINOR_MAX_REL * 100))
    return ("global" if why else "minor"), why


def render_css(vars_, animation):
    lines = [":root{"]
    for k in sorted(vars_):
        lines.append("  %s: %s;" % (k, vars_[k]))
    if animation and animation["name"] != "none":
        lines.append("  --nox-anim: nox-%s %ss ease-in-out infinite;" % (animation["name"], animation["period_s"]))
    else:
        lines.append("  --nox-anim: none;")
    lines.append("}")
    lines.append("@keyframes nox-pulse{0%,100%{opacity:.85}50%{opacity:1}}")
    lines.append("@keyframes nox-breathe{0%,100%{transform:scale(1)}50%{transform:scale(1.02)}}")
    lines.append("@keyframes nox-drift{0%{transform:translate3d(0,0,0)}50%{transform:translate3d(6px,-4px,0)}100%{transform:translate3d(0,0,0)}}")
    lines.append("@media (prefers-reduced-motion: reduce){:root{--nox-anim: none}}")
    return "\n".join(lines) + "\n"


class UIMutator:
    def __init__(self, state_dir, clock=time.time):
        self.dir = state_dir
        self.clock = clock
        self.state_path = os.path.join(state_dir, "ui_state.json")
        self.css_path = os.path.join(state_dir, "ui_overrides.css")
        self.journal_path = os.path.join(state_dir, "ui_journal.jsonl")
        self.st = read_json(self.state_path) or {"version": 0, "vars": {}, "animation": {"name": "none", "period_s": 0},
                                                  "history": [], "pending": [], "trial": None, "next_id": 1}

    def _save(self):
        self.st["history"] = self.st["history"][-MAX_VERSIONS:]
        write_json(self.state_path, self.st)
        with open(self.css_path + ".tmp", "w", encoding="utf-8") as f:
            f.write(render_css(self.st["vars"], self.st["animation"]))
        os.replace(self.css_path + ".tmp", self.css_path)

    def _snapshot(self, note):
        return {"version": self.st["version"], "vars": dict(self.st["vars"]), "animation": dict(self.st["animation"]),
                "ts": self.clock(), "note": note}

    def _apply(self, norm, why, note, trial):
        self.st["history"].append(self._snapshot("до: " + note))
        self.st["vars"].update(norm["vars"])
        if "animation" in norm:
            self.st["animation"] = norm["animation"]
        self.st["version"] += 1
        if trial:
            self.st["trial"] = {"version": self.st["version"], "until": self.clock() + TRIAL_TTL_S,
                                "revert_to": self.st["history"][-1]["version"]}
        self._save()
        journal_add(self.journal_path, {"ts": self.clock(), "action": "apply", "version": self.st["version"],
                                        "change": norm, "why": why, "note": note, "trial": bool(trial)})

    def propose(self, change, reason, dry_run=False):
        """Предложение от NOX. -> {status: applied_trial|pending_owner|rejected, ...}. reason обязателен (журнал «почему»)."""
        if not reason or not str(reason).strip():
            return {"status": "rejected", "error": "нужна причина (почему NOX хочет это изменить)"}
        try:
            norm = validate(change)
            check_contrast({**{k: v[3] for k, v in WHITELIST.items() if v[0] == "color"}, **self.st["vars"], **norm["vars"]})
        except Rejected as e:
            journal_add(self.journal_path, {"ts": self.clock(), "action": "reject_invalid", "error": str(e), "why": reason})
            return {"status": "rejected", "error": str(e)}
        scope, why = classify(norm, self.st["vars"])
        if dry_run:
            return {"status": "dry_run", "scope": scope, "scope_why": why, "normalized": norm}
        if scope == "minor":
            if self.st["trial"]:
                return {"status": "rejected", "error": "уже идёт проба (version %d): подтвердите confirm() или дождитесь tick()" % self.st["trial"]["version"]}
            self._apply(norm, reason, "minor", trial=True)
            return {"status": "applied_trial", "version": self.st["version"], "ttl_s": TRIAL_TTL_S}
        pid = self.st["next_id"]
        self.st["next_id"] += 1
        self.st["pending"].append({"id": pid, "change": norm, "reason": reason, "scope_why": why, "ts": self.clock()})
        self._save()
        journal_add(self.journal_path, {"ts": self.clock(), "action": "pending_owner", "id": pid, "change": norm, "why": reason, "scope_why": why})
        return {"status": "pending_owner", "id": pid, "scope_why": why,
                "ask": "Мессир, хочу изменить: %s. Причина: %s. Согласны?" % (json.dumps(norm, ensure_ascii=False), reason)}

    def approve(self, pid):
        for p in self.st["pending"]:
            if p["id"] == pid:
                self.st["pending"].remove(p)
                self._apply(p["change"], p["reason"], "global approved #%d" % pid, trial=False)
                journal_add(self.journal_path, {"ts": self.clock(), "action": "owner_approved", "id": pid})
                return {"status": "applied", "version": self.st["version"]}
        return {"status": "error", "error": "нет такого предложения"}

    def reject(self, pid):
        for p in self.st["pending"]:
            if p["id"] == pid:
                self.st["pending"].remove(p)
                self._save()
                journal_add(self.journal_path, {"ts": self.clock(), "action": "owner_rejected", "id": pid, "change": p["change"]})
                return {"status": "rejected"}
        return {"status": "error", "error": "нет такого предложения"}

    def confirm(self):
        """Проба стала постоянной (владелец доволен / NOX подтвердил по метрикам)."""
        if not self.st["trial"]:
            return {"status": "no_trial"}
        self.st["trial"] = None
        self._save()
        journal_add(self.journal_path, {"ts": self.clock(), "action": "confirm", "version": self.st["version"]})
        return {"status": "confirmed", "version": self.st["version"]}

    def tick(self):
        """Вызывать раз в минуту: проба с истёкшим TTL откатывается сама."""
        t = self.st["trial"]
        if t and self.clock() >= t["until"]:
            r = self.rollback(t["revert_to"], why="проба не подтверждена за %d с" % TRIAL_TTL_S)
            return {**r, "status": "auto_rolled_back"}
        return {"status": "idle"}

    def rollback(self, version=None, why="откат"):
        hist = self.st["history"]
        if not hist:
            return {"status": "error", "error": "нет истории"}
        snap = hist[-1] if version is None else next((h for h in reversed(hist) if h["version"] == version), None)
        if snap is None:
            return {"status": "error", "error": "версия не найдена"}
        self.st["vars"] = dict(snap["vars"])
        self.st["animation"] = dict(snap["animation"])
        self.st["version"] += 1
        self.st["trial"] = None
        self._save()
        journal_add(self.journal_path, {"ts": self.clock(), "action": "rollback", "to": snap["version"], "why": why})
        return {"status": "rolled_back", "to": snap["version"], "version": self.st["version"]}

    def reset(self):
        """Полный сброс к исходному виду (пустые переопределения)."""
        self.st["history"].append(self._snapshot("до: reset"))
        self.st["vars"], self.st["animation"], self.st["trial"] = {}, {"name": "none", "period_s": 0}, None
        self.st["version"] += 1
        self._save()
        journal_add(self.journal_path, {"ts": self.clock(), "action": "reset"})
        return {"status": "reset"}


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    state = argv[argv.index("--state") + 1] if "--state" in argv else os.environ.get("NOX_STATE", "/root/nox/state")
    m = UIMutator(state)
    c = argv[0]
    if c == "propose":
        ch = json.loads(argv[1])
        r = m.propose(ch.get("change", ch), ch.get("reason", ""), "--dry-run" in argv)
    elif c == "approve":
        r = m.approve(int(argv[1]))
    elif c == "reject":
        r = m.reject(int(argv[1]))
    elif c == "confirm":
        r = m.confirm()
    elif c == "tick":
        r = m.tick()
    elif c == "rollback":
        r = m.rollback(int(argv[1]) if len(argv) > 1 and argv[1].isdigit() else None)
    elif c == "show":
        r = m.st
    elif c == "css":
        print(render_css(m.st["vars"], m.st["animation"]))
        return 0
    else:
        print("unknown", c)
        return 1
    print(json.dumps(r, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
