#!/bin/bash
# c54: включить диспетчер, 6 исполнителей NOX, самообучение, знания; запустить обучение весов (через c52/train_start.sh). STOP-флаг владельца уважается.
a(){ iconv -f utf-8 -t ascii//TRANSLIT -c | cut -c1-220; }
L=/root/nox/logs/c54_start.log; exec > >(tee -a $L) 2>&1; echo "== $(date -Is) c54"
for s in /root/nox/STOP /root/nox/STOP.flag /root/nox/state/STOP /root/nox/state/STOP.flag; do [ -e $s ] && { echo "STOP flag $s -> exit"; exit 0; }; done
echo "== sub-executors definition"; grep -rIl -iE "native_subexecutors|subexecutor" /root/nox/state /root/nox/scripts /root/nox/*.json 2>/dev/null | head -5 | a
echo "== supervisor conf (agents/dispatch/train)"; ls /etc/supervisor/conf.d 2>/dev/null | grep -iE "agent|dispatch|sched|arbiter|self|learn|train|miner|kb-" | head -30
echo "== trainer log tail"; tail -n 12 /root/nox/logs/train_qwen9b_t131u.log 2>/dev/null | a
echo "== volta FATAL"; tail -n 6 /root/nox/logs/nox-train-volta-t866u*.log 2>/dev/null | a
echo "== HOLD cause"; grep -rIn "HOLD_QWEN_REVISION_FILE_SHA" /root/nox/scripts /root/nox/state 2>/dev/null | head -3 | a
echo "== START services"
for s in nox-priority-scheduler nox-selfheal nox-agent-architect-t859u nox-agent-integrator-t859u nox-agent-tuner-t858u nox-dialog-miner nox-self-learning-loop nox-kb-eventlistener nox-checklist-worker nox-hidden-router nox-gpu-watchdog-t865u nox-vram-guard-t829u nox-lifeline-guard; do
  supervisorctl status $s 2>/dev/null | grep -q RUNNING && { echo "$s already RUNNING"; continue; }
  supervisorctl start $s 2>&1 | tail -1 | a; done
sleep 20; echo "== status after"; supervisorctl status | grep -E "agent|priority|selfheal|miner|learning|kb-|checklist|router|guard|train" | awk '{print $1,$2}'
echo "== disk"; df -h / /root /opt 2>/dev/null | a
echo "== training start (c52)"; curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c52/train_start.sh -o /tmp/train_start.sh && nohup bash /tmp/train_start.sh >/root/nox/logs/c52_train_start.out 2>&1 &
sleep 100; tail -n 15 /root/nox/logs/c52_train_start.log 2>/dev/null | a; nvidia-smi --query-gpu=index,utilization.gpu,memory.used --format=csv,noheader
echo done
