#!/bin/bash
S=/workspace/nox/web/site; cd $S
cp -n nox-shell.js nox-shell-classic.js && cp lib/NOX_WEB_UNIFIED/webroot/nox-shell.js nox-shell.js && echo "module nox-shell restored"
n=0; for f in *.html; do grep -q 'src="nox-shell.js"' $f && { sed -i 's#<script src="nox-shell.js" defer></script>#<script src="nox-shell-classic.js" defer></script>#' $f; n=$((n+1)); }; done; echo "pages switched to classic: $n"
cp nox-nav.js nox-nav.js.bak_c300_fx; python3 - <<'P'
p="/workspace/nox/web/site/nox-nav.js"; s=open(p).read()
s=s.replace("/* c300: nox-shell.js здесь классический скрипт без export -> оболочку строит он сам */\nconst mountShell = (window.NoxShell && window.NoxShell.mountShell) || (() => {}); const startTiers = (window.NoxShell && window.NoxShell.startTiers) || (() => {});","import { mountShell, startTiers } from './nox-shell.js';")
open(p,"w").write(s); print("nav import restored", "import { mountShell" in s)
P
# диск: крупнейшее
echo "== disk"; df -h /workspace | tail -1; du -xh --max-depth=2 /workspace 2>/dev/null | sort -rh | head -25
