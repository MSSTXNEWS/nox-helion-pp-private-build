#!/bin/bash
O=/workspace/nox/agent/out
for f in adapter_chain_8510 cascade_8400 embed_8082 web_server core_8090 nox_agents gb10_judge_tunnel; do echo "$f last300KB: $(tail -c 300000 $O/$f.log | grep -a -c -E 'Traceback|refused')  mtime $(stat -c %y $O/$f.log | cut -c1-19)"; done
echo == ops; du -xsh /workspace/nox/ops/* 2>/dev/null | sort -rh | head -6; du -xsh /workspace/nox/backup/* 2>/dev/null | sort -rh | head -4
echo == embed
wc -l /workspace/nox/canon_night/embed_server.py; grep -n -E "model|batch|threads|torch.set_num|ThreadingHTTP|max_length|def " /workspace/nox/canon_night/embed_server.py | head -25 | cut -c1-150
tr '\0' '\n' </proc/560981/environ | grep -E "^(OMP|MKL|TORCH|CUDA)" | head
ss -tnp state established '( sport = :8082 )' | head -8 | cut -c1-150
grep -a -E "POST|GET" $O/embed_8082.log | tail -2 | cut -c1-120
