import re, shutil, time
p="/workspace/nox/web/site/nox-nav.js"; s=open(p).read(); shutil.copy(p,p+".bak_c300_nf_"+time.strftime("%H%M%S"))
s=s.replace("import { mountShell, startTiers } from './nox-shell.js';","/* c300: nox-shell.js здесь классический скрипт без export -> оболочку строит он сам */\nconst mountShell = (window.NoxShell && window.NoxShell.mountShell) || (() => {}); const startTiers = (window.NoxShell && window.NoxShell.startTiers) || (() => {});")
open(p,"w").write(s); print("nav import fixed", "mountShell = (window" in s)
