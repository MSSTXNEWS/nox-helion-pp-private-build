#!/bin/bash
mkdir -p /root/nox/state/flash_bench; cd /root/nox/state/flash_bench; rm -f ALL.done
curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c320/flashopt.py -o /root/nox/flashopt.py 2>&1 | head -2
python3 -m py_compile /root/nox/flashopt.py && echo compiled
pgrep -f flashopt.py >/dev/null && { echo already_running; exit 0; }
setsid nohup python3 /root/nox/flashopt.py > /root/nox/state/flash_bench/driver.out 2>&1 < /dev/null &
sleep 3; pgrep -af flashopt.py | cut -c1-80; tail -n 3 /root/nox/state/flash_bench/driver.out
