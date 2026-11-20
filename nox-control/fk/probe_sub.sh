#!/bin/bash
a(){ iconv -f utf-8 -t ascii//TRANSLIT -c | cut -c1-170; }
cd /root/nox/scripts
echo "== supervisor subagent-ish"; supervisorctl status | grep -iE "subagent|autonomy|pool|dispatch|worker|exec" | a
echo "== env/conf mentions"; grep -rIn -E "subexecutor|SUBEXEC|NORMAL|target|max_workers|MAX_NATIVE|native_cap" owner_subagent_dispatcher.py 2>/dev/null | head -25 | a
echo "== autonomy pool"; grep -nE "N_WORKERS|WORKERS|target|cap|MAX|environ" owner_autonomy_pool.py 2>/dev/null | head -20 | a
echo "== dispatcher cfg"; grep -nE "environ|MAX|cap|NORMAL|workers|THREE|three|3\b" nox_dispatcher_t855u.py 2>/dev/null | head -20 | a
echo "== state files"; ls -t /root/nox/state/dispatcher 2>/dev/null | head -8; ls -t /root/nox/state | grep -iE "subagent|autonomy|dispatch|lease|queue" | head -8
echo "== dispatcher conf"; grep -E "^(command|environment)" /etc/supervisor/conf.d/nox-dispatcher-t855u.conf 2>/dev/null | a
