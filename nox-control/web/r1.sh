#!/bin/bash
cd /root/nox
echo "== core proc"; for pid in $(pgrep -f brain/nox_core.py); do echo pid $pid; tr '\0' ' ' </proc/$pid/cmdline; echo; readlink /proc/$pid/cwd; ps -o ppid=,lstart= -p $pid; done
echo "== launchers"; grep -rl "nox_core.py" scripts repo/nox-control/wow7/deploy src/wow7/deploy 2>/dev/null | head; ls receipts state/v7 | head -40
echo "== grep S1_0 receipts"; grep -l "S1_0[0-8]" receipts/* state/v7/* logs/V7* 2>/dev/null | head -20
for f in receipts/*; do echo "$f $(python3 -c "import json;o=json.load(open('$f'));print(o.get('id'),o.get('ok'),o.get('status'),str(o.get('result'))[:100])" 2>&1 | head -c 160)"; done
echo "== stage scripts head"; for s in 02_dsp 03_speed 05_prime_mem 06_organs 07_voice_web 08_accept; do f=src/wow7/deploy/S1_$s.sh; echo "--- $s ($(wc -l <$f) lines)"; sed -n 1,6p $f | cut -c1-200; grep -noE "nvidia-smi|llama-server|:808[12]|systemctl|pkill|kill |taskset|numactl|CUDA|--model|restart|8091" $f | sort -u -t: -k2 | head -8 | tr '\n' ' '; echo; done
ls src/wow7/deploy/lib_v7.sh; grep -n "^V7\|usage\|RUN" src/wow7/deploy/lib_v7.sh | head -8 | cut -c1-150
