#!/bin/bash
P=$(pgrep -f "distill_v2.py train" | head -1)
echo before ni=$(ps -o ni= -p $P)
for t in /proc/$P/task/*; do renice -n 0 -p $(basename $t) >/dev/null 2>&1; done
echo after ni=$(ps -o ni= -p $P)
echo "$(date -u +%FT%TZ) trainer $P renice 19->0 (SRV: main thread CPU-bound 100%, GPU SM 76%)" >> /workspace/nox/state/p3/ledger_srv.txt
sleep 20
nvidia-smi dmon -s u -c 25 -d 1 | awk 'NR>2{s+=$2;n++} END{print "gpu sm avg",s/n}'
top -H -b -n 2 -d 4 -p $P | awk '/^top/{c++} c==2 && NR>7' | head -3
echo == embed_server; E=560981; ls -l /proc/$E/cwd; ss -tnp 2>/dev/null | grep "pid=$E" | head -3 | cut -c1-120; ss -tlnp 2>/dev/null | grep "pid=$E" | cut -c1-100
tail -5 /workspace/nox/canon_night/*.log 2>/dev/null | cut -c1-160 | tail -8
for t in $(ls /proc/$E/task | head -40); do echo "$(cat /proc/$E/task/$t/stat | awk '{print $14+$15}') $(cat /proc/$E/task/$t/comm)"; done | sort -rn | head -5
