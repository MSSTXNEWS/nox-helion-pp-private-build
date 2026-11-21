#!/bin/bash
echo "== процессы"; ps -eo pid,etimes,pcpu,args | grep -E "llama-server|gateway.py|web_server|stt_server|tts_server|recall|hf download|huggingface|gdown|git clone|npm|wget|curl -|aria2|rclone|python3 .*import|backup" | grep -v grep | cut -c1-170
echo "== диск"; df -h / | tail -1; du -sh /root/nox/dl /root/nox/glm53_disk /dev/shm 2>/dev/null
echo "== загрузки dl"; ls /root/nox/dl; for d in /root/nox/dl/hf/*; do echo "$(du -sh $d | cut -f1) $(basename $d)"; done 2>/dev/null
echo "== логи свежие"; ls -t /root/nox/dl/logs 2>/dev/null | head -5
echo "== память"; python3 - <<'PY'
import sqlite3,glob
for f in glob.glob('/root/nox/**/*.db',recursive=True)[:6]:
    try:
        c=sqlite3.connect(f,timeout=3);print(f,c.execute("select count(*) from mem_facts").fetchone())
    except Exception as e: pass
PY
