#!/bin/bash
S=/workspace/nox/web/site
T=bak_s3_2
RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300
cd $S
for f in nox-ninja.js nox-settings-tabs.js nox-sun-x.css; do [ -f $f.$T ] || { [ -f $f ] && cp $f $f.$T; }; done
for f in nox-ninja.js nox-settings-tabs.js nox-settings-tabs.css nox-worlds.js nox-worlds.css nox-state.js nox-sun-x.css; do curl -fsSL "$RAW/$f" -o /tmp/s3ui_$f && cp /tmp/s3ui_$f $S/$f && echo placed $f; done
nw=0
for f in $S/*.html; do
  grep -q "nox-shell\|nox-nav.js\|nox-pult.js" $f || continue
  grep -q 'nox-worlds.js' $f || { sed -i 's#</head>#<link rel="stylesheet" href="./nox-worlds.css"><script src="./nox-worlds.js"></script>\n</head>#' $f; nw=$((nw+1)); }
  grep -q 'nox-state.js' $f || sed -i 's#</body>#<script src="./nox-state.js"></script>\n</body>#' $f
  grep -q 'nox-cmd.js' $f || sed -i 's#</body>#<script src="./nox-cmd.js" defer></script>\n</body>#' $f
done
echo "worlds injected: $nw"
# nox-state.js должен подключаться раньше остальных скриптов с fetch: переносим в head
for f in $S/*.html; do grep -q 'nox-state.js' $f && ! grep -q 'data-s3state' $f && sed -i 's#<script src="./nox-state.js"></script>#<script src="./nox-state.js" data-s3state></script>#' $f; done
/workspace/nox/venv/bin/python /workspace/nox/qa_ctl.py --pin
grep -c "nox-worlds.js" $S/index.html $S/settings.html $S/scene.html
