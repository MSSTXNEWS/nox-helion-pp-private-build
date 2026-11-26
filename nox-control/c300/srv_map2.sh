#!/bin/bash
N=/workspace/nox
echo "== supervisorctl"; supervisorctl status 2>&1 | head -20 | cut -c1-100
echo "== litellm"; ps -eo pid,etimes,args | grep -E "litellm|privacy_gw" | grep -v grep | cut -c1-150
ls $N/router; python3 - <<'PY'
import re
s=open("/workspace/nox/router/config.yaml",encoding="utf-8").read()
s=re.sub(r"(?im)^(\s*(api_key|key|token|master_key)\s*:).*$",r"\1 ***",s)
print(s[:1800])
PY
echo "== flock/locks"; grep -rl "flock\|fcntl" $N/stewards $N/ops $N/agent $N/svc --include=*.py --include=*.sh 2>/dev/null | grep -v -E "bak|venv" | wc -l
echo "== biggest logs"; find $N -name "*.log" -size +30M -not -path "*/venv*" 2>/dev/null | xargs -r ls -laS 2>/dev/null | head -8 | awk '{print $5,$9}'
echo "== gateway vs litellm ports"; ss -tlnp | grep -E ":(4000|8793|8794|8792|8795|18[0-9]{3}|4001)\b" | awk '{print $4,$6}' | cut -c1-80
echo "== web health scripts"; ls $N/operators 2>/dev/null | head; wc -l $N/operators/watchdog.sh $N/stewards/*.py $N/advisors/gateway.py $N/web/pkg/server/*.py 2>/dev/null | tail -1
echo "== count self-made"; for d in stewards operators ops agent svc; do echo "$d: $(ls $N/$d/*.py $N/$d/*.sh 2>/dev/null | wc -l) файлов"; done
echo "== qa"; ls $N/agent | grep -i qa | head; ls $N/ops | grep -i -E "qa|lighthouse" | head -5; ls ~/.cache/ms-playwright 2>/dev/null | head -3
