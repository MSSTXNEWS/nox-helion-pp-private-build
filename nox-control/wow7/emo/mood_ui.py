"""mood_ui: снимок Affect -> mood_ui.json для веба «Резонанс» (тема, цвет сцены, темп музыки, частота эмодзи).

Темы: HELION (по умолчанию, тёплая уверенность), CHRONOS (порядок/осторожность при тревоге), SOMNIUM (ночь, покой),
FORGE (азарт мастерства), SYNAPSE (любопытство). Гистерезис: тема держится >= MIN_DWELL_S, чтобы сцена не мигала.
CLI: python3 mood_ui.py [--dry-run] [--state DIR] [--out PATH]  (по умолчанию пишет $NOX_STATE/mood_ui.json атомарно).
"""
import os as _os, sys as _sys  # общие модули COMMON (statefile/quiet/fastq/datafence)
for _c in (_os.environ.get("NOX_COMMON", ""), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "COMMON"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "common"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "common")):
    if _c and _os.path.isdir(_c) and _c not in _sys.path:
        _sys.path.append(_c)
import colorsys
import json

import statefile
import os
import sys
import time

THEMES = ("HELION", "CHRONOS", "SOMNIUM", "FORGE", "SYNAPSE")
MIN_DWELL_S = 1200


def pick_theme(snap):
    p, a, _ = snap["mood"]
    dr, fr = snap["drives"], snap["fear"]
    fear_max = max(fr.values()) if fr else 0.0
    if snap.get("quiet") and fear_max < 0.7:
        return "SOMNIUM"
    if fear_max >= 0.5 or snap.get("fear_load", 0) >= 0.4:
        return "CHRONOS"
    if max(dr.get("curiosity", 0), dr.get("knowledge", 0)) >= 0.7 and p >= -0.1:
        return "SYNAPSE"
    if dr.get("mastery", 0) >= 0.7 or (a >= 0.35 and p >= 0.2):
        return "FORGE"
    return "HELION"


def build(snap, prev=None):
    """-> dict mood_ui. prev - прошлый mood_ui (для гистерезиса темы)."""
    now = snap["ts"]
    theme = pick_theme(snap)
    since = now
    if prev and prev.get("theme") in THEMES:
        since = prev.get("since", now)
        if theme != prev["theme"]:
            urgent = theme == "CHRONOS" and max(snap["fear"].values() or [0]) >= 0.7
            if now - since < MIN_DWELL_S and not urgent:
                theme = prev["theme"]
            else:
                since = now
    p, a, d = snap["mood"]
    hue = 220 - 180 * (p + 1) / 2                         # печаль -> синий, радость -> янтарь
    sat = 0.30 + 0.35 * min(1.0, abs(a) + 0.3)
    lit = 0.10 + 0.08 * (a + 1) / 2
    r, g, b = colorsys.hls_to_rgb(hue / 360, lit, sat)
    bpm = round(52 + 56 * (a + 1) / 2)
    if snap.get("quiet"):
        bpm = min(bpm, 60)
    emoji = max(0.0, min(0.35, 0.10 + 0.20 * p + 0.10 * a))
    if snap.get("quiet"):
        emoji = 0.0
    return {
        "theme": theme, "since": since, "ts": now, "mood_label": snap["mood_label"],
        "scene": {"hue": round(hue), "saturation": round(sat, 2), "lightness": round(lit, 2),
                  "hex": "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))},
        "music": {"bpm": bpm, "mode": "major" if p >= 0 else "minor", "intensity": round(max(0.0, min(1.0, 0.5 + 0.5 * a)), 2)},
        "emoji_rate": round(emoji, 2),
        "tone": snap["style"]["notes"],
    }


def write(ui, path):
    statefile.save(path, ui, indent=1)


def main(argv):
    dry = "--dry-run" in argv
    state = argv[argv.index("--state") + 1] if "--state" in argv else os.environ.get("NOX_STATE", "/root/nox/state")
    out = argv[argv.index("--out") + 1] if "--out" in argv else os.path.join(state, "mood_ui.json")
    from affect_loop import Affect
    snap = Affect(state_dir=state).snapshot()
    prev = None
    try:
        with open(out, encoding="utf-8") as f:
            prev = json.load(f)
    except (OSError, ValueError):
        pass
    ui = build(snap, prev)
    if dry:
        print(json.dumps(ui, ensure_ascii=False, indent=1))
    else:
        write(ui, out)
        print("written", out, ui["theme"])


if __name__ == "__main__":
    main(sys.argv[1:])
