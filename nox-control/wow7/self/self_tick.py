"""self_tick: раз в минуту связывает EMO (mood_ui.json/mood.json) с самовыражением: голос, интерфейс, звук. Журналы «почему» - в модулях.
Читает $NOX_STATE: mood_ui.json (EMO/mood_ui.py), mood.json (p,a,d), phase.json {"phase": "adult"} (если нет - adult), tastes.json (мягкий сдвиг звука).
Пишет: voice_profile.json (VoiceDesigner.decide), soundscape_mood.json (веб читает и вызывает NoxSoundscape.setMood), ui_* (UIMutator: только мелкое,
глобальное уйдёт в pending_owner). CLI: python3 self_tick.py [--state DIR] [--dry-run]"""
import os as _os, sys as _sys  # общие модули COMMON (statefile/quiet/fastq/datafence)
for _c in (_os.environ.get("NOX_COMMON", ""), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "COMMON"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "common"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "common")):
    if _c and _os.path.isdir(_c) and _c not in _sys.path:
        _sys.path.append(_c)
import json

from quiet import in_quiet
import os
import sys
import time

from selfcommon import clamp, read_json, write_json
from tastes import Tastes
from ui_mutator import UIMutator
from voice_designer import VoiceDesigner


def read_mood(state):
    m = read_json(os.path.join(state, "mood.json"))
    if isinstance(m, dict):
        pad = m.get("pad") or m
        if all(k in pad for k in ("p", "a")):
            return (pad["p"], pad["a"], pad.get("d", 0.0))
        if isinstance(m.get("mood"), (list, tuple)) and len(m["mood"]) >= 3:
            return tuple(m["mood"][:3])
    ui = read_json(os.path.join(state, "mood_ui.json")) or {}
    mu = ui.get("music")
    if mu:  # грубое восстановление из мажор/минор и интенсивности
        return (0.4 if mu.get("mode") == "major" else -0.4, mu.get("intensity", 0.5) * 2 - 1, 0.0)
    return (0.0, 0.0, 0.0)


def tick(state, dry=False, now=None):
    now = now or time.time()
    night = in_quiet(now)
    mood = read_mood(state)
    phase = (read_json(os.path.join(state, "phase.json")) or {}).get("phase", "adult")
    ui = read_json(os.path.join(state, "mood_ui.json")) or {}
    out = {"mood": mood, "phase": phase, "night": night}
    out["voice"] = VoiceDesigner(state, clock=lambda: now).decide(mood, phase, night, dry_run=dry)
    sm = dict(ui.get("music") or {})
    sm.update({"p": mood[0], "a": mood[1], "d": mood[2], "quiet": night})
    bias = Tastes(state).mood_bias()
    if bias:
        if bias.get("bpm") and "bpm" not in (ui.get("music") or {}):
            sm["bpm"] = bias["bpm"]
        if bias.get("mode") and not (ui.get("music") or {}).get("mode"):
            sm["mode"] = bias["mode"]
        sm["taste_bias"] = bias
    out["soundscape_mood"] = sm
    if not dry:
        write_json(os.path.join(state, "soundscape_mood.json"), sm)
    scene = ui.get("scene") or {}
    if scene.get("hex") and not dry:
        mut = UIMutator(state, clock=lambda: now)
        mut.tick()
        out["ui"] = mut.propose({"vars": {"--nox-accent": scene["hex"]}}, "акцент следует настроению сцены (%s)" % ui.get("mood_label", "?"))
    return out


def main(argv):
    state = argv[argv.index("--state") + 1] if "--state" in argv else os.environ.get("NOX_STATE", "/root/nox/state")
    print(json.dumps(tick(state, "--dry-run" in argv), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
