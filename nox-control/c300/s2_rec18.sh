#!/bin/bash
S=/workspace/nox/web/site
R=$(find /workspace/nox -maxdepth 4 -name svc_registry.json 2>/dev/null | head -1); echo REG=$R
python3 - "$R" <<'PY'
import json,sys
d=json.load(open(sys.argv[1]))
items=d if isinstance(d,list) else d.get('services',d)
s=json.dumps(items,ensure_ascii=False)
import re
for k in ('podcast','whisper','depth','tts2','stt'):
    for m in re.finditer(r'.{0,80}%s.{0,120}'%k,s,re.I): print(k,'::',m.group(0)[:200]); break
PY
ls $S/vendor/transformers-js/dist | head; ls /workspace/nox/models 2>/dev/null | head -20; ls $S/models 2>/dev/null | head
pgrep -fa "podcastfy\|whisper" | head -3 | cut -c1-150
grep -c "editor" $S/nav.json; grep -o '"[^"]*editor[^"]*"' $S/nav.json | head -5
