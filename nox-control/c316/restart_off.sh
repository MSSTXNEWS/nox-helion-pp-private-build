#!/bin/bash
# сервер с --reasoning off (thinking выключен на уровне сервера) + запуск suites v2
cp -n /root/nox/flash_suite_mind.json /dev/null 2>/dev/null
cp /root/nox/state/flash_suite_mind.json /root/nox/state/flash_suite_mind_THINK5_orig.json 2>/dev/null
sed -i 's/--reasoning off //; s/--no-op-offload/--reasoning off --no-op-offload/' /root/nox/start_glm.sh
grep -c "reasoning off" /root/nox/start_glm.sh
nohup setsid bash /root/nox/start_glm.sh > /root/nox/logs/start_glm_off.log 2>&1 < /dev/null &
for i in $(seq 1 60); do sleep 5; [ "$(curl -s -m 2 -o /dev/null -w '%{http_code}' http://127.0.0.1:8081/health)" = 200 ] && break; done
echo up after $((i*5))s
curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c305/flash_bench.py -o /root/nox/flash_bench.py
FB_V2=1 nohup setsid python3 /root/nox/flash_bench.py suites > /root/nox/logs/bench_suites2.log 2>&1 < /dev/null &
sleep 60; tail -n 3 /root/nox/logs/bench_suites2.log | cut -c1-200
