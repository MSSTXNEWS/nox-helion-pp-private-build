#!/bin/bash
N=/workspace/nox
echo "== launchers/refs (files) per port"
for p in 8141 8151 8142 8152 8106; do echo "-- $p"; grep -rIl --exclude-dir=backup --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=venv --exclude-dir=__pycache__ --exclude=*.log --exclude=*.jsonl -E "[: ]$p([^0-9]|$)" $N/ops $N/serve $N/agent $N/stewards $N/judges $N/svc $N/state/*.json $N/router $N/operators $N/web/pkg/server $N/brain 2>/dev/null | grep -v p3_cpuset | head -14; done
echo "== judge_service cfg"; ls $N/judges | head -30; grep -n -E "8141|8142|8151|8152|8106|Llama|gguf|load|model" $N/judges/judge_service.py | cut -c1-170 | head -40
echo "== svc_selfheal 8106"; f=$(grep -rIl "8106" $N/ops $N/serve 2>/dev/null | grep -i heal | head -2); echo "$f"; for x in $f; do grep -n -B2 -A4 8106 $x | cut -c1-220 | head -30; done
echo "== cpu_judges_20261125"; ls $N/ops/cpu_judges_20261125 | head; 
echo "== llama-swap.yaml"; sed -E 's/(key|token)[:=] *[^ ]+/\1: ***/Ig' $N/serve/llama-swap.yaml | cut -c1-200 | head -80
echo "== arbiter slot/8104 refs"; grep -n -E "8104|slot|parallel" $N/agent/arbiter.py | cut -c1-180 | head -20
echo "== serve_stack nox_args"; n=$(grep -n "^nox_args" $N/serve/serve_stack.sh | head -1 | cut -d: -f1); sed -n "${n},$((n+30))p" $N/serve/serve_stack.sh | cut -c1-200
echo "== autotrain mode"; cat $N/agent/autotrain/mode 2>/dev/null; ls $N/agent/autotrain | head; grep -n -E "8104|\-t [0-9]+|--threads|parallel" $N/agent/autotrain/autotrain.sh | cut -c1-200 | head -20
echo "== clients conns now"; for p in 8141 8142 8151 8152 8106 8300; do echo "$p: $(ss -Htnp state established "( dport = :$p )" | grep -o 'users:(("[a-z_.0-9-]*' | sort | uniq -c | tr '\n' ' ')"; done
