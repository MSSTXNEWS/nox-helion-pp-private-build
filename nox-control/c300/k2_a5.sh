echo "C300: k2_a5"
N=/workspace/nox; A=$N/agent/autotrain; ST=$N/state
echo "--- kill 8143 (orch disabled t_coder)"; kill -9 3638858 2>&1; sleep 1; ss -ltn | grep -c ':8143 '; free -g | sed -n 2p
echo "--- parallel 4 in ncmoe22 + known_good"
for f in $A/donor_hybrid.cmd.liska_ncmoe22 $A/donor_hybrid.cmd.known_good; do cp -n $f $f.bak_k2
python3 - "$f" <<'P'
import sys
f=sys.argv[1]; L=open(f).read().split("\n")
for i,x in enumerate(L):
    if x=="--parallel" and i+1<len(L): print(f.split("/")[-1],"parallel",L[i+1],"->4"); L[i+1]="4"
open(f,"w").write("\n".join(L))
P
done
cat > $ST/k2_job3.sh <<'J'
#!/bin/bash
N=/workspace/nox; ST=$N/state; L=$ST/k2_job3.log
log(){ echo "$(date -u +%T) $*" >> $L; }
for i in $(seq 90); do [ $(grep -c "^.*DRAW[0-9]:" $ST/k2_job2.log 2>/dev/null) -ge 3 ] && break; sleep 10; done
sleep 5; log "restart body with ncmoe22 (expert layers on GPU), parallel 4"
for i in $(seq 40); do bash $N/ops/body_restart.sh --cmd $N/agent/autotrain/donor_hybrid.cmd.liska_ncmoe22 --reason "k2: ncmoe22 parallel4 TTFT" >> $L 2>&1 && break; sleep 20; done
V=$(nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader,nounits | awk -F, '{printf "%.1f",100*$1/$2}'); log "VRAM $V%"
awk -v v=$V 'BEGIN{exit !(v>92)}' && { log "VRAM>92 rollback"; bash $N/ops/body_restart.sh --known-good --force --reason "k2 vram rollback" >> $L 2>&1; }
log "slots $(curl -s -m5 localhost:8104/slots | python3 -c 'import sys,json;print(len(json.load(sys.stdin)))')"
log "JOB3 DONE"
J
chmod +x $ST/k2_job3.sh; env RUNNER_TRACKING_ID=k2j3 setsid -f bash $ST/k2_job3.sh </dev/null >/dev/null 2>&1
cat $ST/k2_job2.log | cut -c1-250
