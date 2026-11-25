#!/bin/bash
N=/workspace/nox
for pid in 2843961 2829955 2822667 2715440 1829115 2880442 2881102 2881811; do
 if [ -d /proc/$pid ]; then pp=$(ps -o ppid= -p $pid|tr -d ' '); echo "pid $pid age=$(ps -o etimes= -p $pid)s ni=$(ps -o ni= -p $pid) cwd=$(readlink /proc/$pid/cwd) ppid=$pp($(tr '\0' ' ' </proc/$pp/cmdline 2>/dev/null | cut -c1-70)) :: $(tr '\0' ' ' </proc/$pid/cmdline | cut -c1-130)"; else echo "pid $pid gone"; fi
done
echo "== current clients (all with ports)"; ss -Htnp state established '( dport = :8104 )' | grep -o 'users:(("[^"]*",pid=[0-9]*' | sort | uniq -c
echo "== 8141"; P=$(pgrep -f "port 8141"|head -1); ps -o pid,stat,ni,etimes -p $P; grep -E "State" /proc/$P/status; cat $N/state/train_cpu_pause.json 2>/dev/null | head -c 300; echo
timeout 20 curl -s -m 15 127.0.0.1:8141/health; echo; timeout 25 curl -s -m 20 127.0.0.1:8141/v1/chat/completions -H 'Content-Type: application/json' -d '{"model":"mgr_core","messages":[{"role":"user","content":"hi"}],"max_tokens":5}' | head -c 300; echo
echo "== who stops 8141 (orch freeze logic)"; grep -n -E "SIGSTOP|kill.*STOP|-STOP|freeze|заморо" /workspace/nox/stewards/nox_orch.py | cut -c1-190 | head -10
echo "== cascade 8400 -> 8104 usage"; grep -rn --include=*.py -E "8104|NOX_SEED_URL|n_parallel|max_inflight" /workspace/nox/ops/cascade* /workspace/nox/brain/CASCADE 2>/dev/null | cut -c1-160 | head -8; ls -la /proc/2715440/cwd 2>&1 | sed 's/.*-> //'
echo "== nox_agents tasks hitting donor (recent decisions)"; tail -n 5 /workspace/nox/state/orch/decisions.jsonl | cut -c1-260
echo "== slot detail"; curl -s -m3 127.0.0.1:8104/slots | python3 -c "
import sys,json
for s in json.load(sys.stdin):
    p=s.get('params',{}); nt=s.get('next_token',[{}])[0]; print(s['id'],'proc',s['is_processing'],'n_dec',nt.get('n_decoded'),'max',p.get('max_tokens'),'temp',p.get('temperature'),'stream',p.get('stream'), 'n_ctx_prompt', s.get('n_prompt_tokens') or s.get('prompt_n'))"
