#!/bin/bash
a(){ iconv -f utf-8 -t ascii//TRANSLIT -c | cut -c1-170; }
cd /root/nox/scripts
echo "== MODES/DEFAULT"; grep -nE "^(MODES|DEFAULT_WORKER_CAP)|MODES *=|DEFAULT_WORKER_CAP *=" owner_subagent_dispatcher.py | a
N=$(grep -n "^MODES" owner_subagent_dispatcher.py | head -1 | cut -d: -f1); [ -n "$N" ] && sed -n "${N},$((N+8))p" owner_subagent_dispatcher.py | a
echo "== callers"; grep -rn "worker_cap" --include=*.py . 2>/dev/null | grep -v "def \|owner_subagent_dispatcher.py" | grep -v "/state/" | head -10 | a
echo "== autonomy mode state"; python3 -c "import json;d=json.load(open('/root/nox/state/owner_autonomy_mode_v15.json'));print(json.dumps(d,ensure_ascii=True)[:600])" 2>&1 | a
echo "== dispatcher status"; python3 -c "import json;d=json.load(open('/root/nox/state/dispatcher_status.json'));print(json.dumps(d,ensure_ascii=True)[:700])" 2>&1 | a
echo "== env of dispatcher proc"; tr '\0' '\n' < /proc/$(pgrep -f nox_dispatcher_t855u.py | head -1)/environ 2>/dev/null | grep -E "NOX_DISPATCHER|WORKER|CAP" | a
echo "== supervisor dispatcher conf"; ls /etc/supervisor/conf.d | grep -iE "dispatch|subag|autonom" ; grep -hE "^(command|environment)" /etc/supervisor/conf.d/*dispatcher* 2>/dev/null | a
