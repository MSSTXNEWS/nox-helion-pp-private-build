#!/bin/bash
S=/root/nox/dl/v7/exec2/nox_wow
mkdir -p /root/nox/receipts/bak_B /root/nox/logs
for p in $(pgrep -f llama-server); do echo "PID $p: $(tr '\0' ' ' </proc/$p/cmdline | cut -c1-600)"; done | tee /root/nox/receipts/bak_B/glm_cmdline_$(date +%s).txt
echo "load: $(cat /proc/loadavg)"; nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader
for p in $(pgrep -f llama-server); do ps -o pid,pcpu,etime,rss -p $p|tail -1; done
bash $S/SPD/recon_s1.sh > /root/nox/logs/recon_B.txt 2>&1; echo "recon rc=$?"
cut -c1-220 /root/nox/logs/recon_B.txt | head -40
