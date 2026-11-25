#!/bin/bash
# bundle c_ghost: Ghost-Tab во всех полях. Бэкап, установка, откат при ошибке.
S=/workspace/nox/web/site; B=$(dirname "$0"); cd $S || exit 1
for f in chat.html advisors.html assistant.html; do [ -f $f ] || continue
  [ -f $f.bak_c_ghost ] || cp -p $f $f.bak_c_ghost
  grep -q nox-ghost-all.js $f || python3 - "$f" <<'PY'
import sys,re
f=sys.argv[1]; s=open(f,encoding="utf-8").read()
tag='<script src="./nox-ghost-all.js?v=c1" defer></script>'
if "nox-ghost.js" in s:
    s=re.sub(r'(<script[^>]*nox-ghost\.js[^>]*></script>)', lambda m:m.group(1)+"\n"+tag, s, 1)
elif "</body>" in s:
    s=s.replace("</body>", '<script src="./nox-ghost.js" defer></script>\n'+tag+"\n</body>",1)
open(f,"w",encoding="utf-8").write(s); print("patched",f)
PY
done
cp $B/nox-ghost-all.js $S/nox-ghost-all.js
curl -s -m5 localhost:8091/web/nox-ghost-all.js | head -c 60; echo
