#!/bin/bash
echo "== before"; ps -eo pid,etimes,pcpu,args --sort=-pcpu | grep -vE "llama-server|web_server|gateway|embed_server|nox_life|recall|stt|tts|voice|glm_watch|sshd|ps -eo|grep|c300|bash$" | head -12 | cut -c1-120
crontab -l 2>/dev/null | grep -v '^#' | cut -c1-120
pkill -f 'strings -n 8'; pkill -f flash_bench.py; pkill -f exp_driver; pkill -f 'c252/poll.sh'; pkill -f '/tmp/sr.sh'; pkill -f glm_tune.py
for p in $(pgrep -f 'while true|sleep 1[0-9][0-9]?$'); do tr '\0' ' ' </proc/$p/cmdline | grep -qE 'poll|sr\.sh|raw.githubusercontent' && kill $p && echo "killed loop $p"; done
sleep 2; echo "== after"; ps -eo pid,pcpu,args --sort=-pcpu | head -8 | cut -c1-110; cat /proc/loadavg
