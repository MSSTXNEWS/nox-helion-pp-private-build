#!/bin/bash
curl -s -m3 127.0.0.1:8400/health | head -c 120; echo
kill 2715440; sleep 1
for i in $(seq 1 12); do sleep 2; curl -fs -m2 127.0.0.1:8400/health >/dev/null 2>&1 && { echo "up after $((i*2+1))s"; break; }; done
curl -s -m3 127.0.0.1:8400/health | head -c 160; echo
pgrep -af "python -m cascade" | cut -c1-90
sleep 20; tail -3 /workspace/nox/agent/out/cascade_watchdog.log | cut -c1-120; tail -c 3000 /workspace/nox/agent/out/cascade_8400.log | grep -a -c "address already"
echo "$(date -u +%FT%TZ) SRV: убит осиротевший cascade 2715440 (держал :8400, watchdog 74194 29683 раз падал bind), watchdog поднял свой" >> /workspace/nox/state/p3/ledger_srv.txt
