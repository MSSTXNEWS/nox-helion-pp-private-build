"""selftool self_atlas: расширение selftools/self_map.py. Кладётся в nox-control/selftools/ и добавляется в MODULES registry.py.
Режимы: scan (пересобрать атлас), ask (ответ из атласа), read (человекочитаемое устройство)."""
import os
import sys

import registry as R

sys.path.insert(0, os.environ.get("NOX_WORLD_DIR", "/root/nox/src/wow7/world"))
import self_atlas as SA  # noqa: E402

STATE = os.environ.get("NOX_STATE", "/root/nox/state")


@R.register("self_atlas", "read", {"properties": {
    "mode": {"type": "string", "default": "ask"}, "question": {"type": "string", "default": "как ты устроен?"}}},
    "Atlas of self: processes, ports, models, GPU/RAM, repo modules and call graph; answers about own structure from the atlas.")
def self_atlas(a):
    if a.get("mode") == "scan":
        atlas = SA.build_atlas(R.REPO + "/nox-control", os.environ.get("NOX_MODEL_DIRS", "/root/nox/models").split(":"))
        SA.save(atlas, STATE)
        return {"ok": True, "ports": len(atlas["ports"]), "modules": len(atlas["repo"]), "models": len(atlas["models"])}
    try:
        atlas = SA.load(STATE)
    except OSError:
        return {"ok": False, "error": "атласа ещё нет: self_atlas mode=scan"}
    if a.get("mode") == "read":
        return {"ok": True, "text": SA.describe(atlas)}
    return {"ok": True, "text": SA.answer(a.get("question", ""), atlas)}
