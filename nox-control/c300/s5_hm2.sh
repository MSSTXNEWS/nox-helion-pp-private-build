#!/bin/bash
cat > /tmp/s5_patch_handmade.py <<'PYEOF'
import json, re, sys, shutil, time, py_compile
QA = sys.argv[1]; REGF = sys.argv[2] if len(sys.argv) > 2 else None
s = open(QA, encoding="utf-8").read()
if "HANDMADE" in s: print("already"); sys.exit(0)
ts = time.strftime("%Y%m%d%H%M")
shutil.copy(QA, QA + ".bak_s5_" + ts)
DON = '''HANDMADE = {"chat": "assistant-ui, Deep Chat, React Flow, highlight.js", "index": "Gridstack, Sortable.js, Tremor, ECharts", "cinema": "Swiper, Video.js/Plyr, hls.js", "music": "wavesurfer.js, Howler, Plyr", "news": "Swiper, Tremor, Shoelace", "photo": "Cropper.js, Fabric.js/Konva, Shoelace", "studio": "Konva, Fabric.js, Shoelace, Motion", "tools": "cmdk, ninja-keys, Shoelace", "consciousness": "llm-viz, 3d-force-graph, three.js, ECharts", "organism": "ECharts, 3d-force-graph, cosmos.gl", "soul": "3d-force-graph, cosmos.gl, React Flow", "growth": "ECharts, Tremor", "selffeel": "ECharts, Tremor", "training": "ECharts, Tremor, Grafana-стиль"}
'''
s = s.replace("DANGER_OK = True", "DANGER_OK = True\n" + DON, 1)
s = s.replace('"neon\\":true/false,', '"neon\\":true/false,\\"handmade\\":true/false (интерфейс свёрстан вручную/выглядит самодельно, колхозно, топорно вместо готовых профессиональных компонентов),', 1)
if '\\"handmade\\"' not in s:
    s = s.replace('neon\\":true/false', 'neon\\":true/false,\\"handmade\\":true/false (интерфейс свёрстан вручную или выглядит самодельно, топорно, колхозно вместо готовых профессиональных компонентов)', 1)
new = '''    hm = bool(j.get("handmade")) or bool(j.get("toporno"))
    if len(CHECK) >= 23:
        item(23, "rework" if hm else ("ok" if j else "manual"), ("самодельный/топорный интерфейс, взять готовые модули из DONORS.md: " + HANDMADE.get(key, "см. DONORS.md") + "; замечания: " + str(j.get("toporno"))[:300]) if hm else "")
'''
s = s.replace('    if j.get("patterns_missing")', new + '    if j.get("patterns_missing")', 1)
open(QA, "w", encoding="utf-8").write(s); py_compile.compile(QA, doraise=True); print("patched", QA)
if REGF:
    r = json.load(open(REGF, encoding="utf-8"))
    if len(r["checklist"]) < 23:
        shutil.copy(REGF, REGF + ".bak_s5_" + ts)
        r["checklist"].append({"n": 23, "text": "Готовые профессиональные модули из DONORS.md, без самодельной вёрстки и «колхоза»; иначе возврат с указанием модуля"})
        json.dump(r, open(REGF, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("checklist", len(r["checklist"]), r["checklist"][0])
PYEOF
/workspace/nox/venv/bin/python /tmp/s5_patch_handmade.py /workspace/nox/qa_audit.py /workspace/nox/web/site/qa/registry.json
grep -c HANDMADE /workspace/nox/qa_audit.py
md5sum /workspace/nox/qa_audit.py
