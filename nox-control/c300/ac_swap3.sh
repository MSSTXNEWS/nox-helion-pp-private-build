echo "C300: ac_swap3"
P=$(pgrep -f "port 8812" | head -1)
mkdir -p /workspace/nox/state/accel
tr '\0' ' ' </proc/$P/cmdline > /tmp/c8812.txt; cat /tmp/c8812.txt; echo
ex=$(ps -o ni= -p $P); echo "ni $ex"
echo "== load before"; l1=$(cut -d' ' -f1 /proc/loadavg); top -bn2 -d 20 | grep -E "^%Cpu" | tail -1
{ echo '#!/bin/bash'; echo "# restore :8812 (accel 26.11) — cwd: $(readlink /proc/$P/cwd)"; echo "cd $(readlink /proc/$P/cwd) && setsid nohup taskset -c 4-7,20-23 nice -n 10 $(cat /tmp/c8812.txt) >/tmp/llama8812.log 2>&1 </dev/null &"; } > /workspace/nox/state/accel/restore_8812.sh; chmod +x /workspace/nox/state/accel/restore_8812.sh
kill $P; sleep 5; pgrep -f "port 8812" | wc -l
sleep 30; echo "== after"; top -bn2 -d 20 | grep -E "^%Cpu" | tail -1; cat /proc/loadavg
head -30 /workspace/nox/serve/llama-swap.yaml | cut -c1-160
