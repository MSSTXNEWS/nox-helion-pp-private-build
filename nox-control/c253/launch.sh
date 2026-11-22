#!/bin/bash
curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c253/exp_driver.py -o /root/nox/exp_driver_B.py
pgrep -f exp_driver_B >/dev/null && { echo "уже идёт"; exit 0; }
pkill -f glm_watch.sh; sleep 1
nohup setsid python3 /root/nox/exp_driver_B.py > /root/nox/logs/B_exp.out 2>&1 &
sleep 90; cat /root/nox/logs/B_exp.out | cut -c1-400
grep -E 'usage|numactl|^#' /root/nox/dl/v7/v4/nox_wow/OPT/numa_tune.sh | head -8 | cut -c1-200
which numactl
