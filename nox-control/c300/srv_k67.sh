echo "C300: srv_k67"
cd /workspace/nox
date -u +%T; tail -n 4 ops/dpo/run2.log | tr '\r' '\n' | tail -n 3 | cut -c1-200
echo == procs CPU
ps -eo pid,ppid,etimes,pcpu,pmem,rss,args --sort=-pcpu | head -25 | cut -c1-190
echo == RAM; free -g | head -2; nproc
echo == gpu; nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader
echo == listen; ss -ltnp 2>/dev/null | awk '{print $4,$6}' | grep -o ":[0-9]* .*pid=[0-9]*" | sed 's/users:(("//;s/",pid=/ /' | sort -t: -k2 -n | head -60
ls ops/liska_restart_core.py; sed -n '1,25p' ops/liska_restart_core.py | cut -c1-200
awk '/^class live_turn/{p=1} p{print; n++} n>30{exit}' integration/adapter.py | cut -c1-170
