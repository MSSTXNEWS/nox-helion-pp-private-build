#!/bin/bash
# Только чтение: факты по задачам 6V14-01, 5V14-01, 1V14-06, 3A03, 6A04
a(){ iconv -f utf-8 -t ascii//TRANSLIT -c | cut -c1-150; }
echo "== 6V14-01 dispatcher"; supervisorctl status | grep -iE "dispatch|arbiter|scheduler" | a
ls -t /root/nox/logs 2>/dev/null | grep -i dispatch | head -3
echo "== 5V14-01 web"; curl -s -m 8 -o /dev/null -w "web29 %{http_code} size %{size_download}\n" http://127.0.0.1:18775/
ls /root/nox/web* -d 2>/dev/null | head -5
echo "== 1V14-06 stop"; grep -nE "stop|STOP|abort|cancel" /root/nox/scripts/chat_proxy.py | grep -E "@app|def " | a | head -8
echo "== 3A03 fts"; grep -rlE "fts5|FTS5|WarmS03" /root/nox/scripts 2>/dev/null | head -5
echo "== 6A04 gpu"; nvidia-smi --query-gpu=index,utilization.gpu,memory.used,memory.total --format=csv,noheader
