#!/bin/bash
# c58: только чтение — 6 исполнителей, тёплые веса на ПК владельца (Tailscale), оптимизации.
a(){ iconv -f utf-8 -t ascii//TRANSLIT -c | cut -c1-210; }
echo "== time $(date -Is)"
echo "== tailscale"; tailscale status 2>&1 | head -8 | a
echo "== warm cache docs/config"; ls /root/nox/state | grep -iE "warm|pc_|owner_pc|sync" | head -10; ls /root/nox/scripts | grep -iE "warm|pc_sync|offload|owner_pc" | head -10
for f in /root/nox/state/warm*.json /root/nox/state/*warm*; do [ -f "$f" ] && { echo "-- $f"; head -c 500 "$f" | a; echo; }; done 2>/dev/null | head -20
echo "== offload service log"; tail -n 5 $(ls -t /root/nox/logs/*offload* 2>/dev/null | head -1) 2>/dev/null | a
echo "== subexecutors"; F=$(grep -rIl "native_subexecutors" /root/nox/state /root/nox/scripts 2>/dev/null | head -2); echo "$F"
for f in $F; do grep -n -iE "subexecutor" $f | head -10 | a; done
echo "== agents list"; supervisorctl status | grep -iE "agent|teacher|miner|checklist|router|hunter|worm|distill|nano|kb-" | awk '{print $1,$2}'
echo "== optimizations (env/flags)"; ps -eo args | grep "[l]lama-server" | head -2 | cut -c1-300; cat /root/nox/state/task_boost_mode.json 2>/dev/null | head -c 300
echo "== disk"; df -h / | tail -1; du -xsh /root/nox/models/* 2>/dev/null | sort -rh | head -5
echo "== run_train_t131u.sh"; sed -n 1,45p /root/nox/scripts/run_train_t131u.sh | a
echo "== gpu total"; nvidia-smi --query-gpu=index,name,memory.total,memory.used --format=csv,noheader; nvidia-smi --query-compute-apps=pid,gpu_uuid,used_memory --format=csv,noheader | head -6
