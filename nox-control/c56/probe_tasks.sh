#!/bin/bash
# c56: только чтение — как NOX берёт задачи, что он делал после запуска, состояние обучения.
a(){ iconv -f utf-8 -t ascii//TRANSLIT -c | cut -c1-230; }
echo "== time $(date -Is)"; df -h / | tail -1
echo "== checklist-worker cmd"; supervisorctl status nox-checklist-worker | awk '{print $1,$2,$3,$4}'; grep -rl "nox-checklist-worker" /etc/supervisor 2>/dev/null | head -2 | xargs -r grep -hE "^command|^directory" | a
echo "== task files"; ls -la --time-style=+%F_%T /root/nox/state 2>/dev/null | grep -iE "task|check|queue|backlog|todo|boost|wave|journal" | awk '{print $5,$6,$7}' | head -25
echo "== task_boost_mode"; cat /root/nox/state/task_boost_mode.json 2>/dev/null | head -c 600; echo
echo "== scripts with task queue"; grep -lE "task_queue|work_tasks|checklist|TASK_QUEUE|tasks\.json" /root/nox/scripts/*.py 2>/dev/null | head -12
echo "== checklist worker log"; tail -n 14 $(ls -t /root/nox/logs/*checklist* 2>/dev/null | head -1) 2>/dev/null | a
echo "== agent logs"; for f in $(ls -t /root/nox/logs/*agent* /root/nox/logs/*dispatch* /root/nox/logs/*scheduler* /root/nox/logs/*self_learn* 2>/dev/null | head -4); do echo "-- $f"; tail -n 5 $f | a; done
echo "== training"; supervisorctl status | grep -iE "train|learn|distill" | awk '{print $1,$2}'; tail -n 4 /root/nox/logs/train_qwen9b_t131u.log 2>/dev/null | a; nvidia-smi --query-gpu=index,utilization.gpu,memory.used --format=csv,noheader
echo "== expediter journal tail"; tail -n 6 /root/nox/state/expediter_journal.csv 2>/dev/null | a
echo "== api status"; curl -s -m8 127.0.0.1:8091/api/nox/status | head -c 500 | a; echo; curl -s -m8 127.0.0.1:8091/api/nox/training/status | head -c 500 | a; echo
echo "== process list api"; curl -s -m8 127.0.0.1:8091/api/nox/system/processes | head -c 400 | a; echo
