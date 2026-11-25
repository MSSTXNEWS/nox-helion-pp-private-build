#!/bin/bash
echo "C300: p2_missing"; N=/workspace/nox; S=$N/web/pkg/server
echo "## /img/generate contract"; grep -n 'img/generate\|/img/\|def .*img' $S/web_server.py $S/creative_proxy.py 2>/dev/null | cut -c1-200 | head -30
echo "## creative_proxy imgs"; grep -n 'def \|NOX_IMG\|8500\|imgsvc\|18[0-9][0-9][0-9]' $S/creative_proxy.py 2>/dev/null | cut -c1-180 | head -50
echo "## live /img/generate probe (GET)"; curl -s -m 5 -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8091/img/generate; curl -s -m 5 http://127.0.0.1:8091/img/health | head -c 300; echo
echo "## references to missing paths"
FILES="$N/agent/autotrain/autotrain.sh $N/svc/*.sh $N/serve/*.sh $N/ops/*.sh $N/web/pkg/server/*.sh $N/web/pkg/server/svc_registry.json $N/stewards/orch_registry.json $N/stewards/*.py $N/agent/nox_agents/*.py $N/agent/nox_ops/*.py $N/brain/BRAIN/*.py $N/web/pkg/server/*.py /etc/supervisor/conf.d/*.conf"
crontab -l 2>/dev/null > /tmp/p2_cron.txt
grep -ohE '/workspace/nox/[A-Za-z0-9_./-]+' $FILES /tmp/p2_cron.txt 2>/dev/null | sed -E 's/[.,:;)]+$//' | sort -u > /tmp/p2_paths.txt
wc -l < /tmp/p2_paths.txt
while read -r p; do case "$p" in *.log|*.pid|*/tmp/*|*/state/*|*/agent/out/*|*.lock|*/STOP*|*.off|*.tmp|*.bak*|*/out/*|*_2026*.json|*/web_conv/*) continue;; esac; [ -e "$p" ] || echo "$p"; done < /tmp/p2_paths.txt | head -120
echo "## who references (top missing dirs)"; for d in ops/v5_ready_reserve_20261125 ops/draw ops/v5_knowledge_gpu_20261125; do echo "$d exists=$([ -e $N/$d ] && echo yes || echo NO)"; done
echo "## import/file errors in logs (last 4h)"
find $N/agent/out $N/state $N/stewards $N/svc -maxdepth 3 -name '*.log' -mmin -240 2>/dev/null | head -150 | xargs grep -lE 'ModuleNotFoundError|ImportError|FileNotFoundError|No such file or directory' 2>/dev/null | head -25 | while read f; do echo "-- $f"; grep -hE 'ModuleNotFoundError|ImportError|FileNotFoundError|No such file or directory' "$f" | tail -2 | cut -c1-200; done
echo "## DONE"
