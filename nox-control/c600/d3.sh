#!/bin/bash
for p in $(pgrep -f "rte_server.py|nox_core.py|glm53/gateway.py|web_server.py"); do echo "pid $p $(tr '\0' ' ' </proc/$p/cmdline|cut -c1-90)"; tr '\0' '\n' </proc/$p/environ | grep -E "^(NOX_|RTE_)" | grep -viE "key|token|secret|pass" | tr '\n' ' ' | cut -c1-600; echo; done
echo "== souls"; for f in /root/nox/PRIME/soul_prime_v3.txt /root/nox/repo/nox-control/glm53/soul_prime_v3.txt /root/nox/src/wow7/prime/soul_prime_v3.txt; do echo "$f $(md5sum <$f 2>&1|cut -c1-8) $(wc -c <$f 2>&1) kor=$(grep -c коротко $f 2>&1)"; done
ls -d /root/nox/PRIME /root/nox/repo/.git 2>&1; git -C /root/nox/repo log --oneline -1 2>&1 | cut -c1-80
echo "== logs"; ls -la --time-style=+%H:%M /root/nox/logs | awk '{print $5,$6,$7}' | tail -25
